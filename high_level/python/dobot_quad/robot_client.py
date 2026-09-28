#!/usr/bin/env python3
"""
Robot gRPC Client Library
Simplifies connection, execution, and cancellation for all examples.

Usage:
    from dobot_quad import RobotClient

    robot = RobotClient("192.168.5.2:50051")

    # State switching (no 'set_' prefix)
    robot.balance_stand()
    robot.set_target_state("walk")
    robot.change_mode()

    # Balance motions (value in degrees/meters, duration in seconds)
    robot.balance_pitch(15.0, duration=2.0, mode="dynamic")
    robot.balance_height(-0.05, duration=3.0, mode="static")
    robot.balance_neutral()

    # Line walk & rotation
    robot.walk_forward(3.0)
    robot.rotate_left(90)

    # Velocity sequence
    robot.velocity_sequence([(0.5,0,0,2), (0,0,0,1)])
"""

import atexit
import grpc
import signal
import sys
import time
import warnings

from enum import IntEnum
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from .proto import grpc_service_pb2 as pb
from .proto import grpc_service_pb2_grpc as pb_grpc

# =====================================================================
# Constants
# =====================================================================

#: Valid FSM state names (used by set_target_state, case-insensitive).
VALID_STATES = frozenset(
    {
        "passive",
        "ready",
        "stand_down",
        "balance_stand",
        "walk",
        "flying_trot",
        "rl",
        "gongxi",
        "dance0",
        "wave",
        "jump",
        "backflip",
        "recovery",
    }
)

#: Valid balance motion IDs.
VALID_BALANCE_MOTIONS = frozenset(
    {
        "balance_pitch",
        "balance_yaw",
        "balance_roll",
        "balance_height",
        "balance_neutral",
    }
)

#: Valid choreography atomic action names (MINI_QUAD only).
#: Each is a server-side motion id; the server transparently handles any
#: state switching the action needs and returns to WALK when it finishes.
VALID_ATOMIC_ACTIONS = frozenset(
    {
        "twirl_jump",   # 跳跃转体 (mimic, 0.7s)
        "diag_step",    # 对角迈步 (mimic, 5.9s)
        "hop_step",     # 前腿蹦跳迈步 (mimic, 3.0s)
        "groove",       # 摇摆律动 (8s)
        "bounce",       # 点头弹跳 (6s)
        "body_wave",    # 身体波浪 (8s)
        "hip_circle",   # 扭屁股/臀画圆 (8s)
        "head_circle",  # 扭头/头画圆 (8s)
    }
)

#: Post-trigger sleep per atomic action: action duration + ~1s settle margin.
#: The server stream finishes on arrival at the action state; the action body
#: runs during this sleep and the robot returns to WALK by itself.
ATOMIC_ACTION_POST_SLEEP_SECONDS = {
    "twirl_jump": 2.0,
    "diag_step": 7.0,
    "hop_step": 4.0,
    "groove": 9.0,
    "bounce": 7.0,
    "body_wave": 9.0,
    "hip_circle": 9.0,
    "head_circle": 9.0,
}

#: Valid gait names for velocity_sequence.
VALID_GAITS = frozenset({"walk", "flying_trot"})

#: Valid FSM state names for MINI_QUAD_WHEEL (轮足).
VALID_WHEEL_STATES = frozenset(
    {
        "passive",
        "ready",
        "stand_down",
        "wheel_loco",
        "drift",
        "climb",
        "handstand",
    }
)

#: Valid gait names for velocity_sequence on MINI_QUAD_WHEEL.
VALID_WHEEL_GAITS = frozenset({"wheel_loco"})

#: Direction name → int mapping for line_walk.
DIRECTION_MAP = {
    "forward": 0,
    "front": 0,
    "backward": 1,
    "back": 1,
    "left": 2,
    "right": 3,
}

#: Default post-state-switch sleep for regular state wrappers.
DEFAULT_STATE_POST_SLEEP_SECONDS = 2.0

#: Single-axis/pose target offset limits in BALANCE_STAND.
#: These values are offsets from initial posture to target posture.
BALANCE_ROLL_LIMIT_DEG = 17.0
BALANCE_PITCH_LIMIT_DEG = 11.5
BALANCE_YAW_LIMIT_DEG = 11.5
BALANCE_HEIGHT_MIN_M = -0.08
BALANCE_HEIGHT_MAX_M = 0.0

#: Dance configurable duration constraints.
DEFAULT_DANCE_SECONDS = 126.5
MIN_DANCE_SECONDS = 4.0
MAX_DANCE_SECONDS = 128.0

#: Wave configurable first waiting time, with fixed tail wait.
DEFAULT_WAVE_SECONDS = 5.0
FIXED_WAVE_TAIL_SECONDS = 2.0



class Leg(IntEnum):
    """Leg and fill-light identifiers (maps to proto LegName)."""

    FL = 1          # Front-left leg light
    FR = 2          # Front-right leg light
    RL = 3          # Rear-left leg light
    RR = 4          # Rear-right leg light
    FILL_FRONT = 5  # Front fill light
    FILL_BACK = 6   # Rear fill light


class Color(IntEnum):
    """Predefined LED colors (converted to RGB via _color_to_rgb)."""

    OFF = 0
    RED = 1
    ORANGE = 2
    YELLOW = 3
    GREEN = 4
    CYAN = 5
    BLUE = 6
    PURPLE = 7
    WHITE = 8


@dataclass
class LegLedConfig:
    """Per-leg RGB and brightness entry for batch SetLeds requests."""

    leg: Leg
    r: int = 0              # Red channel [0, 255]
    g: int = 0              # Green channel [0, 255]
    b: int = 0              # Blue channel [0, 255]
    brightness: int = -1    # [0, 255]; -1 keeps cached brightness



# =====================================================================
# Validation Utilities (reusable across all API methods)
# =====================================================================

def _color_to_rgb(color: Color) -> Tuple[int, int, int]:
    """Convert a predefined Color to an (r, g, b) tuple."""
    mapping = {
        Color.OFF: (0, 0, 0),
        Color.RED: (255, 0, 0),
        Color.ORANGE: (255, 165, 0),
        Color.YELLOW: (255, 255, 0),
        Color.GREEN: (0, 255, 0),
        Color.CYAN: (0, 255, 255),
        Color.BLUE: (0, 0, 255),
        Color.PURPLE: (128, 0, 128),
        Color.WHITE: (255, 255, 255),
    }
    return mapping.get(color, (0, 0, 0))


# Main leg lights in stable wire order for SetLeds padding.
_MAIN_LEGS: Tuple[Leg, ...] = (Leg.FL, Leg.FR, Leg.RL, Leg.RR)


def _is_leg_light(leg: Leg) -> bool:
    """Return True if leg is one of the four main leg lights."""
    return leg in _MAIN_LEGS


def _validate_leg_light(leg: Leg) -> None:
    """Reject fill lights for leg-LED set APIs."""
    if not _is_leg_light(leg):
        raise ValueError(
            "Leg LED set APIs only support FL, FR, RL, RR; "
            "fill lights (FILL_FRONT/FILL_BACK) are not supported"
        )


def _leg_name(leg: Leg) -> str:
    return leg.name if hasattr(leg, "name") else str(leg)


def _scale_rgb_by_brightness(r: int, g: int, b: int, brightness: int) -> Tuple[int, int, int]:
    """Bake brightness into RGB for hardware that ignores the brightness field.

    Logical color (r,g,b) is kept in the client cache; only the wire payload is scaled:
    channel' = round(channel * brightness / 255).
    """
    bri = int(_clamp(brightness, 0, 255))
    if bri >= 255:
        return int(r), int(g), int(b)
    if bri <= 0:
        return 0, 0, 0
    return (
        (int(r) * bri + 127) // 255,
        (int(g) * bri + 127) // 255,
        (int(b) * bri + 127) // 255,
    )


def _clamp(value, lo, hi):
    """Clamp a numeric value to [lo, hi]."""
    return max(lo, min(hi, value))


def clamp_speed_ratio(ratio):
    """Clamp speed ratio to [10, 100]."""
    return _clamp(int(ratio), 10, 100)


def clamp_distance(distance):
    """Clamp distance to [0, 3] meters."""
    return _clamp(float(distance), 0.0, 3.0)


def clamp_angle(angle):
    """Clamp angle to [0, 3600] degrees (allows up to 10 full rotations)."""
    return _clamp(float(angle), 0.0, 3600.0)


def clamp_angle_signed(angle):
    """Clamp angle to [-180, 180] degrees for rotate_walk.

    Negative angles represent counter-clockwise (left turn).
    Positive angles represent clockwise (right turn).
    """
    return _clamp(float(angle), -180.0, 180.0)


def clamp_turns(turns):
    """Clamp turns to [1, 10]."""
    return _clamp(int(turns), 1, 10)


def clamp_balance_value(value, axis):
    """Clamp balance target value: degrees for rpy, meters for height."""
    if axis == "height":
        return _clamp(float(value), BALANCE_HEIGHT_MIN_M, BALANCE_HEIGHT_MAX_M)  # only downward
    if axis == "roll":
        return _clamp(float(value), -BALANCE_ROLL_LIMIT_DEG, BALANCE_ROLL_LIMIT_DEG)
    if axis == "pitch":
        return _clamp(float(value), -BALANCE_PITCH_LIMIT_DEG, BALANCE_PITCH_LIMIT_DEG)
    if axis == "yaw":
        return _clamp(float(value), -BALANCE_YAW_LIMIT_DEG, BALANCE_YAW_LIMIT_DEG)
    if axis == "neutral":
        return 0.0
    # Fallback for unknown axis keys.
    return _clamp(float(value), -BALANCE_PITCH_LIMIT_DEG, BALANCE_PITCH_LIMIT_DEG)


def clamp_balance_duration(duration):
    """Clamp single-axis/balance-sequence duration to [0.5, 5] seconds."""
    return _clamp(float(duration), 0.5, 5.0)


def clamp_pose_duration(duration):
    """Clamp composite pose duration to [1, 5] seconds."""
    return _clamp(float(duration), 1.0, 5.0)


#: Aliases for state names (source -> canonical name registered on server).
STATE_ALIASES = {
    "emergency": "passive",
    # ``choreo`` was renamed to ``gongxi`` in v1.3.0. The alias is kept so that
    # legacy ``set_target_state("choreo")`` calls keep working; the dedicated
    # ``choreo()`` method below additionally emits a DeprecationWarning.
    "choreo": "gongxi",
}


def validate_state(state_name):
    """Validate and normalize a state name (case-insensitive).

    Returns:
        Lowercased state name.

    Raises:
        ValueError: If state_name is not in VALID_STATES or VALID_WHEEL_STATES.
    """
    norm = state_name.strip().lower()
    norm = STATE_ALIASES.get(norm, norm)
    all_valid = VALID_STATES | VALID_WHEEL_STATES
    if norm not in all_valid:
        raise ValueError(f"Unknown state '{state_name}'. " f"Valid states: {sorted(all_valid)}")
    return norm


def validate_atomic_action(action_name):
    """Validate and normalize an atomic action name (case-insensitive).

    Returns:
        Lowercased action name.

    Raises:
        ValueError: If action_name is not in VALID_ATOMIC_ACTIONS.
    """
    norm = action_name.strip().lower()
    if norm not in VALID_ATOMIC_ACTIONS:
        raise ValueError(
            f"Unknown atomic action '{action_name}'. "
            f"Valid actions: {sorted(VALID_ATOMIC_ACTIONS)}"
        )
    return norm


def validate_balance_motion(motion_id):
    """Validate a balance motion ID.

    Raises:
        ValueError: If motion_id is not in VALID_BALANCE_MOTIONS.
    """
    if motion_id not in VALID_BALANCE_MOTIONS:
        raise ValueError(
            f"Unknown balance motion '{motion_id}'. " f"Valid: {sorted(VALID_BALANCE_MOTIONS)}"
        )


def validate_gait(gait):
    """Validate and normalize a gait name (case-insensitive).

    Returns:
        Lowercased gait name.

    Raises:
        ValueError: If gait is not in VALID_GAITS or VALID_WHEEL_GAITS.
    """
    norm = gait.strip().lower()
    all_valid = VALID_GAITS | VALID_WHEEL_GAITS
    if norm not in all_valid:
        raise ValueError(f"Unknown gait '{gait}'. Valid: {sorted(all_valid)}")
    return norm


def resolve_direction(direction):
    """Resolve a walk direction to int (0-3).

    Accepts int (0-3) or string ('forward'/'front'/'backward'/'back'/'left'/'right').

    Raises:
        ValueError: If direction is invalid.
    """
    if isinstance(direction, str):
        norm = direction.strip().lower()
        if norm not in DIRECTION_MAP:
            raise ValueError(
                f"Unknown direction '{direction}'. " f"Valid: {list(DIRECTION_MAP.keys())} or 0-3"
            )
        return DIRECTION_MAP[norm]
    else:
        direction = int(direction)
        if direction not in (0, 1, 2, 3):
            raise ValueError(
                f"direction must be 0(front)/1(back)/2(left)/3(right), " f"got {direction}"
            )
        return direction


def resolve_rotate_direction(direction):
    """Resolve a rotation direction to int (0=left, 1=right).

    Accepts int (0/1) or string ('left'/'right').

    Raises:
        ValueError: If direction is invalid.
    """
    if isinstance(direction, str):
        norm = direction.strip().lower()
        if norm not in ("left", "right"):
            raise ValueError("rotate direction must be 'left' or 'right'")
        return 0 if norm == "left" else 1
    else:
        direction = int(direction)
        if direction not in (0, 1):
            raise ValueError("rotate direction must be 0(left) or 1(right)")
        return direction


class RobotClient:
    """Simple client for the robot gRPC service."""

    def __init__(self, addr="192.168.5.2:50051"):
        self.channel = grpc.insecure_channel(addr)
        self.stub = pb_grpc.gRPCServiceStub(self.channel)
        # 视频子系统需要裸 IP（RTSP :8554 / go2rtc :1984 / GControll :22000）
        self._host = str(addr).rsplit(":", 1)[0].strip("[]")
        self._video_manager = None
        # Seed local state from server, then ensure OA is on.
        # We track these locally because GetRobotState is eventually
        # consistent and may return stale values right after a Set* RPC.
        res = self.get_state()
        self._speed_ratio = res.current_speed_ratio if res.success else 50
        self._obstacle_avoidance = True
        self._robot_type = None
        self._led_cache: dict[Leg, tuple[int, int, int, int]] = {}
        # self.set_obstacle_avoidance(True)

    # =================================================================
    # Core RPC: Query
    # =================================================================

    def get_motions(self):
        """Get available motions."""
        return self.stub.GetAvailableMotions(pb.GetMotionsRequest())

    def get_state(self):
        """Get current robot state."""
        return self.stub.GetRobotState(pb.GetRobotStateRequest())

    def get_current_state_name(self) -> str:
        """Get just the current FSM state name string."""
        res = self.get_state()
        return res.current_state if res.success else ""

    def get_speed_ratio(self) -> int:
        """Get the current speed ratio."""
        return self._speed_ratio

    def get_obstacle_avoidance(self) -> bool:
        """Get the current obstacle avoidance state."""
        return self._obstacle_avoidance

    def get_robot_type(self) -> str:
        """Get the robot type string (e.g. 'miniQuad' or 'miniQuadW').
        Cached after first successful query."""
        if not self._robot_type:
            res = self.get_state()
            if res.success:
                self._robot_type = res.robot_type
        return self._robot_type

    def is_quad(self) -> bool:
        """Check if connected robot is MINI_QUAD (点足)."""
        return self.get_robot_type() == "miniQuad"

    def is_quad_wheel(self) -> bool:
        """Check if connected robot is MINI_QUAD_WHEEL (轮足)."""
        return self.get_robot_type() == "miniQuadW"

    # =================================================================
    # Core RPC: Configuration
    # =================================================================

    def set_speed_ratio(self, ratio: int):
        """Set speed ratio [10-100]."""
        ratio = clamp_speed_ratio(ratio)
        resp = self.stub.SetSpeedRatio(pb.SetSpeedRatioRequest(speed_ratio=ratio))
        self._speed_ratio = resp.current_speed_ratio
        return resp

    def set_obstacle_avoidance(self, enable):
        """Enable/disable obstacle avoidance. Accepts bool or "on"/"off"."""
        if isinstance(enable, str):
            norm = enable.strip().lower()
            if norm not in ("on", "off"):
                raise ValueError("set_obstacle_avoidance only accepts bool or 'on'/'off'")
            enable = norm == "on"
        resp = self.stub.SetObstacleAvoidance(pb.SetObstacleAvoidanceRequest(enable=bool(enable)))
        self._obstacle_avoidance = resp.current_enabled
        return resp


    def set_legs_rgb(
        self,
        configs: List[LegLedConfig],
        default_brightness: int = -1,
        verbose: bool = False
    ) -> bool:
        """Batch-set RGB and brightness for leg lights FL/FR/RL/RR (single RPC).

        Current-version rule (all-or-nothing user control): every SetLeds always
        carries all four main legs in FL/FR/RL/RR order.

          * Legs present in ``configs`` use the given RGB/brightness.
          * Legs already in the client cache (previous user set) are resent
            unchanged so incremental APIs (e.g. set_leg_brightness) keep other
            legs lit.
          * Legs never set in this session are padded as RGB=0 (off).

        Brightness is applied by baking into wire RGB
        (channel * brightness / 255). The wire ``brightness`` field is always
        sent as 255, because some firmwares ignore dimming via that field and
        may keep prior intensity when brightness==0 while still applying RGB.
        The client cache keeps logical (unscaled) RGB + brightness so hue is
        preserved across set_leg_brightness calls.

        Fill lights (FILL_FRONT/FILL_BACK) are rejected. Duplicate legs in
        ``configs``: last entry wins.

        Args:
            configs: Per-leg color/brightness entries.
            default_brightness: Fallback when config.brightness == -1; uses
                cache or 255 if unset.
            verbose: Print full command dump and status messages.

        Returns:
            True if the server accepted the request, False on RPC error.

        Raises:
            ValueError: If any RGB channel is outside [0, 255], or if a fill
                light target is used.
        """
        if not configs:
            return True

        # Resolve explicit overrides (last duplicate wins).
        explicit: dict[Leg, tuple[int, int, int, int, str]] = {}
        for cfg in configs:
            _validate_leg_light(cfg.leg)

            if not (0 <= cfg.r <= 255) or not (0 <= cfg.g <= 255) or not (0 <= cfg.b <= 255):
                raise ValueError(f"RGB values must be 0-255, got ({cfg.r},{cfg.g},{cfg.b})")

            if cfg.brightness >= 0:
                final_brightness = int(_clamp(cfg.brightness, 0, 255))
            else:
                if default_brightness >= 0:
                    final_brightness = int(_clamp(default_brightness, 0, 255))
                else:
                    cached = self._led_cache.get(cfg.leg)
                    if cached:
                        final_brightness = cached[0]
                    else:
                        final_brightness = 255

            explicit[cfg.leg] = (final_brightness, cfg.r, cfg.g, cfg.b, "explicit")

        req = pb.SetLedsRequest()
        dump_lines: List[str] = []

        for leg in _MAIN_LEGS:
            if leg in explicit:
                bri, r, g, b, source = explicit[leg]
            elif leg in self._led_cache:
                bri, r, g, b = self._led_cache[leg]
                source = "cache"
            else:
                bri, r, g, b = 255, 0, 0, 0
                source = "pad-off"

            self._led_cache[leg] = (bri, r, g, b)

            wire_r, wire_g, wire_b = _scale_rgb_by_brightness(r, g, b, bri)
            # Always 255 on the wire: dimming is conveyed solely via scaled RGB.
            wire_brightness = 255

            cmd = req.commands.add()
            cmd.leg = leg.value
            cmd.brightness = wire_brightness
            cmd.r = wire_r
            cmd.g = wire_g
            cmd.b = wire_b

            dump_lines.append(
                f"  {_leg_name(leg)}: logical rgb({r},{g},{b}) bri={bri} "
                f"-> wire rgb({wire_r},{wire_g},{wire_b}) brightness={wire_brightness} "
                f"[{source}]"
            )

        if verbose:
            print(f"[LED] SetLeds commands ({len(req.commands)}):")
            for line in dump_lines:
                print(line)

        try:
            resp = self.stub.SetLeds(req)
            if not resp.accepted:
                if verbose:
                    print(f"[LED] Batch rejected: {resp.message}")
                return False
            if verbose:
                print("[LED] Batch accepted.")
            return True
        except grpc.RpcError as e:
            print(f"[LED] gRPC error: {e.code().name} - {e.details()}")
            return False
    
    def set_leg_rgb(
        self,
        leg: Leg,
        r: int,
        g: int,
        b: int,
        brightness: int = -1,
        verbose: bool = False
    ) -> bool:
        """Set RGB for a single leg light (FL/FR/RL/RR only).

        Args:
            leg: Target leg light (not fill lights).
            r, g, b: Color channels [0, 255].
            brightness: [0, 255]; -1 keeps cached brightness (default 255).
            verbose: Print status messages.
        """
        return self.set_legs_rgb(
            [LegLedConfig(leg=leg, r=r, g=g, b=b, brightness=brightness)],
            default_brightness=-1,
            verbose=verbose
        )

    def set_leg_color(
        self,
        leg: Leg,
        color: Color,
        verbose: bool = False
    ) -> bool:
        """Set a predefined color on a single leg (brightness from cache)."""
        r, g, b = _color_to_rgb(color)
        return self.set_leg_rgb(leg, r, g, b, brightness=-1, verbose=verbose)

    def set_leg_brightness(
        self,
        leg: Leg,
        brightness: int,
        verbose: bool = False
    ) -> bool:
        """Adjust brightness only; hue is taken from cache (white if unset)."""
        cached = self._led_cache.get(leg)
        if cached:
            _, r, g, b = cached
        else:
            r, g, b = 255, 255, 255
        return self.set_leg_rgb(leg, r, g, b, brightness=brightness, verbose=verbose)

    def set_all_legs_rgb(
        self,
        r: int,
        g: int,
        b: int,
        brightness: int = 255,
        verbose: bool = False
    ) -> bool:
        """Set all four main leg lights (FL/FR/RL/RR) to the same RGB."""
        configs = [
            LegLedConfig(leg=Leg.FL, r=r, g=g, b=b, brightness=brightness),
            LegLedConfig(leg=Leg.FR, r=r, g=g, b=b, brightness=brightness),
            LegLedConfig(leg=Leg.RL, r=r, g=g, b=b, brightness=brightness),
            LegLedConfig(leg=Leg.RR, r=r, g=g, b=b, brightness=brightness),
        ]
        return self.set_legs_rgb(configs, verbose=verbose)

    def set_all_legs_color(
        self,
        color: Color,
        brightness: int = 255,
        verbose: bool = False
    ) -> bool:
        """Set all four main leg lights to a predefined color."""
        r, g, b = _color_to_rgb(color)
        return self.set_all_legs_rgb(r, g, b, brightness, verbose)

    def turn_off_leg(self, leg: Leg, verbose: bool = False) -> bool:
        """Turn a leg light off (RGB=0) while keeping user control and cached brightness."""
        cached = self._led_cache.get(leg)
        brightness = cached[0] if cached else 255
        return self.set_leg_rgb(leg, 0, 0, 0, brightness=brightness, verbose=verbose)

    def reset_legs(
        self,
        legs: Optional[List[Leg]] = None,
        verbose: bool = False
    ) -> bool:
        """Release LED control to the robot's default logic.

        Args:
            legs: Legs to reset; None or empty list resets all legs and fill lights.
            verbose: Print status messages.

        Returns:
            True if the server accepted the request, False on RPC error.
        """
        req = pb.ResetLedsRequest()
        if legs:
            for leg in legs:
                req.legs.append(leg.value)

        try:
            resp = self.stub.ResetLeds(req)
            if not resp.accepted:
                if verbose:
                    print(f"[LED] Reset rejected: {resp.message}")
                return False

            if legs:
                for leg in legs:
                    self._led_cache.pop(leg, None)
            else:
                self._led_cache.clear()

            if verbose:
                target = "all legs" if not legs else f"{len(legs)} leg(s)"
                print(f"[LED] Control released for {target}.")
            return True
        except grpc.RpcError as e:
            print(f"[LED] gRPC error on reset: {e.code().name} - {e.details()}")
            return False
    
    # =================================================================
    # Core RPC: Execution
    # =================================================================

    def execute(self, *motions, loop=False, show_progress=True):
        """
        Execute a motion sequence with real-time progress streaming.
        Each argument can be:
          - str:   motion_id with no parameters
          - tuple: (motion_id, {key: value, ...}) with parameters
        Returns the final SequenceProgress message, or None if cancelled.
        """
        seq = pb.MotionSequence(sequence_id="seq", loop=loop)
        for item in motions:
            if isinstance(item, str):
                seq.motions.add(motion_id=item)
            else:
                mid, params = item[0], item[1]
                m = seq.motions.add(motion_id=mid)
                for k, v in params.items():
                    if isinstance(v, bool):
                        m.parameters.add(key=k, bool_value=v)
                    elif isinstance(v, int):
                        m.parameters.add(key=k, int_value=v)
                    elif isinstance(v, float):
                        m.parameters.add(key=k, float_value=v)
                    elif isinstance(v, str):
                        m.parameters.add(key=k, string_value=v)

        req = pb.ExecuteSequenceRequest(sequence=seq, immediate_start=True)
        print("Running... (Ctrl+C to stop)")

        last_line = ""
        try:
            for p in self.stub.ExecuteSequence(req):
                if p.is_final:
                    if not p.success:
                        print(f"Error: {p.message}")
                    else:
                        print("Done.")
                    return p
                if show_progress:
                    line = (
                        f"  [{p.current_index+1}/{p.total_motions}] "
                        f"{p.current_motion_id} | state: {p.current_state}"
                    )
                    if p.message:
                        line += f" ({p.message})"
                    if line != last_line:
                        print(line)
                        last_line = line
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Cancelled.")
            else:
                print(f"RPC error: {e.code().name} - {e.details()}")
            return None
        return None

    # =================================================================
    # State Switching
    # =================================================================

    def set_target_state(self, target_state: str, show_progress=True):
        """Switch to a target state by name. Case-insensitive.

        Raises:
            ValueError: If target_state is not a valid state name.
        """
        norm = validate_state(target_state)
        return self.execute(norm, show_progress=show_progress)

    def passive(self, show_progress=True):
        """急停（立即进入被动模式）。"""
        return self._set_state_with_delay(
            "passive", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def emergency(self, show_progress=True):
        """急停的别名（映射到 passive）。"""
        return self.passive(show_progress)

    def ready(self, show_progress=True):
        """缓慢趴下（从任意状态平滑过渡）。"""
        return self._set_state_with_delay("ready", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress)

    def stand_down(self, show_progress=True):
        return self._set_state_with_delay(
            "stand_down", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def balance_stand(self, show_progress=True):
        return self._set_state_with_delay(
            "balance_stand", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def walk(self, show_progress=True):
        """切换到行走状态。"""
        return self._set_state_with_delay("walk", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress)

    def rl(self, show_progress=True):
        """切换到 RL 状态。"""
        return self._set_state_with_delay("rl", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress)

    def flying_trot(self, show_progress=True):
        """切换到奔跑状态。"""
        return self._set_state_with_delay(
            "flying_trot", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def gongxi(self, show_progress=True):
        """切换到 GONGXI 状态。"""
        return self._set_state_with_delay("gongxi", 11.5, show_progress)

    def choreo(self, show_progress=True):
        """[已废弃] v1.2.0 的旧方法名，等价于 :meth:`gongxi`。

        ``choreo`` 状态自 v1.3.0 起更名为 ``gongxi``（恭喜/作揖）。本方法仅为
        兼容旧代码保留，调用时会发出 ``DeprecationWarning``，并将在后续版本中移除。
        """
        warnings.warn(
            "RobotClient.choreo() has been renamed to gongxi(); "
            "use gongxi() instead. choreo() will be removed in a future release.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.gongxi(show_progress=show_progress)

    def dance0(self, show_progress=True, duration=DEFAULT_DANCE_SECONDS):
        duration = self._validate_dance_duration(duration)
        return self._set_state_with_delay("dance0", duration, show_progress)

    def dance(self, duration=DEFAULT_DANCE_SECONDS, show_progress=True):
        """积木块别名：跳舞。"""
        return self.dance0(show_progress=show_progress, duration=duration)

    def wave(self, duration=DEFAULT_WAVE_SECONDS, show_progress=True):
        duration = self._validate_non_negative_duration(duration, "wave duration")

        first = self._set_state_with_delay("wave", duration, show_progress)
        if not self._is_success(first):
            return first

        second = self.execute("wave", show_progress=show_progress)
        if not self._is_success(second):
            return second

        time.sleep(FIXED_WAVE_TAIL_SECONDS)
        return second

    def wave_hand(self, duration=DEFAULT_WAVE_SECONDS, show_progress=True):
        """积木块别名：打招呼。"""
        return self.wave(duration=duration, show_progress=show_progress)

    def jump(self, show_progress=True):
        """积木块别名：跳跃。"""
        return self._set_state_with_delay("jump", 3.0, show_progress)

    def backflip(self, show_progress=True):
        return self._set_state_with_delay(
            "backflip", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def recovery(self, show_progress=True):
        return self._set_state_with_delay("recovery", 4.0, show_progress)

    def change_mode(self, show_progress=True):
        """切换腿部构型（膝盖模式切换）。"""
        return self.execute("change_mode", show_progress=show_progress)

    # =================================================================
    # Choreography Atomic Actions (MINI_QUAD only)
    # =================================================================

    def atomic_action(self, action_name: str, show_progress=True):
        """Trigger a choreography atomic action by name. Case-insensitive.

        The server handles any state switching the action needs and returns
        to WALK when the action finishes; this call sleeps through the
        action duration (plus settle margin) after a successful trigger.

        Raises:
            ValueError: If action_name is not a valid atomic action.
        """
        norm = validate_atomic_action(action_name)
        res = self.execute(norm, show_progress=show_progress)
        if self._is_success(res):
            time.sleep(ATOMIC_ACTION_POST_SLEEP_SECONDS[norm])
        return res

    def twirl_jump(self, show_progress=True):
        """跳跃转体（mimic 策略，约 0.7s）。"""
        return self.atomic_action("twirl_jump", show_progress)

    def diag_step(self, show_progress=True):
        """对角迈步（mimic 策略，约 5.9s）。"""
        return self.atomic_action("diag_step", show_progress)

    def hop_step(self, show_progress=True):
        """前腿蹦跳迈步（mimic 策略，约 3.0s）。"""
        return self.atomic_action("hop_step", show_progress)

    def groove(self, show_progress=True):
        """摇摆律动（WBC 体动，8s）。"""
        return self.atomic_action("groove", show_progress)

    def bounce(self, show_progress=True):
        """点头弹跳（WBC 体动，6s）。"""
        return self.atomic_action("bounce", show_progress)

    def body_wave(self, show_progress=True):
        """身体波浪（WBC 体动，8s）。"""
        return self.atomic_action("body_wave", show_progress)

    def hip_circle(self, show_progress=True):
        """扭屁股（臀画圆，WBC 体动，8s）。"""
        return self.atomic_action("hip_circle", show_progress)

    def head_circle(self, show_progress=True):
        """扭头（头画圆，WBC 体动，8s）。"""
        return self.atomic_action("head_circle", show_progress)

    # =================================================================
    # State Switching – MINI_QUAD_WHEEL (轮足)
    # =================================================================

    def wheel_loco(self, show_progress=True):
        """切换到 WHEEL_LOCO 状态（轮足）。"""
        return self._set_state_with_delay(
            "wheel_loco", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    def drift(self, show_progress=True):
        """切换到 DRIFT 状态（轮足）。"""
        return self._set_state_with_delay("drift", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress)

    def climb(self, show_progress=True):
        """切换到 CLIMB 状态（轮足）。"""
        return self._set_state_with_delay("climb", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress)

    def handstand(self, show_progress=True):
        """切换到 HANDSTAND 状态（轮足）。"""
        return self._set_state_with_delay(
            "handstand", DEFAULT_STATE_POST_SLEEP_SECONDS, show_progress
        )

    # =================================================================
    # Velocity Sequence
    # =================================================================

    @staticmethod
    def make_velocity_string(steps):
        """Convert list of (vx, vy, vyaw, duration) tuples to velocity sequence string."""
        if not steps:
            return ""
        return ";".join(f"{vx},{vy},{vyaw},{dur}" for vx, vy, vyaw, dur in steps) + ";"

    def velocity_sequence(
        self, vel_seq, gait="walk", speed_ratio=None, stand_down_after=True, show_progress=True
    ):
        """Execute a velocity sequence.

        Args:
            vel_seq: "vx,vy,vyaw,dur;..." string OR list of tuples.
            gait: "walk" or "flying_trot".
            speed_ratio: [10-100] or None to use current base speed ratio.
            stand_down_after: Append stand_down at the end.

        Raises:
            ValueError: If gait is not valid.
        """
        if isinstance(vel_seq, (list, tuple)):
            vel_seq = self.make_velocity_string(vel_seq)

        norm_gait = validate_gait(gait)

        prev_sr = None
        if speed_ratio is not None:
            speed_ratio = clamp_speed_ratio(speed_ratio)
            prev_sr = self._speed_ratio
            self.set_speed_ratio(speed_ratio)

        prev_oa = self._obstacle_avoidance
        # self.set_obstacle_avoidance(False)

        gait_map = {
            "walk": "walk_velocity_seq",
            "flying_trot": "flying_trot_velocity_seq",
            "wheel_loco": "wheel_loco_velocity_seq",
        }
        motion_id = gait_map[norm_gait]
        motions = [(motion_id, {"velocity_sequence": vel_seq})]
        if stand_down_after:
            motions.append("stand_down")

        try:
            res = self.execute(*motions, show_progress=show_progress)
        finally:
            # self.set_obstacle_avoidance(prev_oa)
            if prev_sr is not None:
                self.set_speed_ratio(prev_sr)
        return res

    # =================================================================
    # Balance Motions
    # =================================================================

    def _balance_motion(self, motion_id, value, duration, mode, show_progress):
        """Internal: execute a single balance motion.

        Raises:
            ValueError: If motion_id is not a valid balance motion.
        """
        validate_balance_motion(motion_id)
        axis = motion_id.replace("balance_", "")
        value = clamp_balance_value(value, axis)
        if axis == "yaw":
            value = -value
        duration = clamp_balance_duration(duration)
        return self.execute(
            "balance_stand",
            (
                motion_id,
                {
                    "value": value,
                    "duration": duration,
                    "mode": mode,
                },
            ),
            show_progress=show_progress,
        )

    def balance_pitch(self, value, duration=2.0, mode="dynamic", show_progress=True):
        """Pitch (nod). value in degrees, >0: forward, <0: backward. [-11.5, 11.5]"""
        return self._balance_motion("balance_pitch", value, duration, mode, show_progress)

    def balance_yaw(self, value, duration=2.0, mode="dynamic", show_progress=True):
        """Yaw (look). value in degrees, >0: right, <0: left. [-11.5, 11.5]"""
        return self._balance_motion("balance_yaw", value, duration, mode, show_progress)

    def balance_roll(self, value, duration=2.0, mode="dynamic", show_progress=True):
        """Roll (lean). value in degrees, >0: left, <0: right. [-17.0, 17.0]"""
        return self._balance_motion("balance_roll", value, duration, mode, show_progress)

    def balance_height(self, value, duration=2.0, mode="dynamic", show_progress=True):
        """Height. value in meters, <0: squat. [-0.08, 0.0]"""
        return self._balance_motion("balance_height", value, duration, mode, show_progress)

    def balance_neutral(self, duration=0.5, show_progress=True):
        """Return all balance axes to neutral."""
        return self._balance_motion("balance_neutral", 0.0, duration, "dynamic", show_progress)

    def balance_sequence(self, motions, show_progress=True):
        """Execute a batch of balance motions in a single RPC call.

        Args:
            motions: list of (motion_id, value, duration, mode) tuples.

        Raises:
            ValueError: If any motion_id is not a valid balance motion.
        """
        items = ["balance_stand"]
        for motion_id, value, duration, mode in motions:
            validate_balance_motion(motion_id)
            axis = motion_id.replace("balance_", "")
            value = clamp_balance_value(value, axis)
            if axis == "yaw":
                value = -value
            duration = clamp_balance_duration(duration)
            items.append((motion_id, {"value": value, "duration": duration, "mode": mode}))
        return self.execute(*items, show_progress=show_progress)

    # =================================================================
    # Line Walk
    # =================================================================

    def line_walk(self, direction=0, distance=3.0, speed_ratio=None, show_progress=True):
        """Walk in a straight line.

        Args:
            direction: 0/"forward", 1/"backward", 2/"left", 3/"right".
            distance: meters [0, 3].
            speed_ratio: [10, 100] or None to use current base speed ratio.

        Raises:
            ValueError: If direction is invalid.
        """
        direction = resolve_direction(direction)
        distance = clamp_distance(distance)

        prev_sr = None
        if speed_ratio is not None:
            speed_ratio = clamp_speed_ratio(speed_ratio)
            prev_sr = self._speed_ratio
            self.set_speed_ratio(speed_ratio)

        prev_oa = self._obstacle_avoidance
        # self.set_obstacle_avoidance(False)
        try:
            res = self.execute(
                ("line_walk", {"direction": direction, "distance": distance}),
                show_progress=show_progress,
            )
        finally:
            # self.set_obstacle_avoidance(prev_oa)
            if prev_sr is not None:
                self.set_speed_ratio(prev_sr)
        return res

    def walk_forward(self, distance=3.0, speed_ratio=None, show_progress=True):
        return self.line_walk(0, distance, speed_ratio, show_progress)

    def walk_backward(self, distance=3.0, speed_ratio=None, show_progress=True):
        return self.line_walk(1, distance, speed_ratio, show_progress)

    def move_left(self, distance=3.0, speed_ratio=None, show_progress=True):
        return self.line_walk(2, distance, speed_ratio, show_progress)

    def move_right(self, distance=3.0, speed_ratio=None, show_progress=True):
        return self.line_walk(3, distance, speed_ratio, show_progress)

    # =================================================================
    # Rotation
    # =================================================================

    def rotate(self, direction="left", angle=90.0, show_progress=True):
        """Rotate in place.

        Args:
            direction: "left"/"right" or 0/1.
            angle: degrees [0, 3600].

        Raises:
            ValueError: If direction is invalid.
        """
        direction = resolve_rotate_direction(direction)
        angle = clamp_angle(angle)
        return self.execute(
            ("rotation", {"direction": direction, "angle": angle}),
            show_progress=show_progress,
        )

    def rotate_left(self, angle=90.0, show_progress=True):
        return self.rotate("left", angle, show_progress)

    def rotate_right(self, angle=90.0, show_progress=True):
        return self.rotate("right", angle, show_progress)

    def circle(self, direction="left", turns=1, show_progress=True):
        """旋转指定圈数。turns: 1~10。"""
        turns = clamp_turns(turns)
        return self.rotate(direction, angle=turns * 360.0, show_progress=show_progress)

    def rotate_walk(self, angle=0.0, distance=0.0, speed_ratio=None, show_progress=True):
        """向 angle 方向移动 distance 米：先旋转再前进。

        Args:
            angle: degrees [-180, 180]. Negative = counter-clockwise (left), Positive = clockwise (right).
            distance: meters [0, 3].
            speed_ratio: [10, 100] or None to use current base speed ratio.
        """
        angle = clamp_angle_signed(angle)
        distance = clamp_distance(distance)

        if angle >= 0:
            first = self.rotate("right", angle, show_progress)
        else:
            first = self.rotate("left", -angle, show_progress)
        if first is None or (hasattr(first, "success") and not first.success):
            return first
        return self.walk_forward(distance, speed_ratio, show_progress)

    # =================================================================
    # Pose Blocks
    # =================================================================

    def dynamic_pose(
        self,
        duration=2.0,
        roll_deg=0.0,
        pitch_deg=0.0,
        yaw_deg=0.0,
        height_m=0.0,
        show_progress=True,
    ):
        """动态姿势：所有轴同时做正弦扫描。

        Args:
            duration: 持续时间（秒），钳位到 [1, 5]。
            roll_deg:   横滚角度（度）[-17.0, 17.0]，0 不动。
            pitch_deg:  俯仰角度（度）[-11.5, 11.5]，0 不动。
            yaw_deg:    偏航角度（度）[-11.5, 11.5]，>0 向右，<0 向左，0 不动。
            height_m:   高度偏移（米）[-0.08, 0.0]，0 不动。
        """
        return self._pose_motion(
            "dynamic_pose",
            duration,
            roll_deg,
            pitch_deg,
            yaw_deg,
            height_m,
            show_progress,
        )

    def static_pose(
        self,
        duration=2.0,
        roll_deg=0.0,
        pitch_deg=0.0,
        yaw_deg=0.0,
        height_m=0.0,
        show_progress=True,
    ):
        """静态姿势：升到目标后保持，结束后回零。

        Args:
            duration: 保持时间（秒），钳位到 [1, 5]。
            roll_deg:   横滚角度（度）[-17.0, 17.0]，0 不动。
            pitch_deg:  俯仰角度（度）[-11.5, 11.5]，0 不动。
            yaw_deg:    偏航角度（度）[-11.5, 11.5]，>0 向右，<0 向左，0 不动。
            height_m:   高度偏移（米）[-0.08, 0.0]，0 不动。
        """
        return self._pose_motion(
            "static_pose",
            duration,
            roll_deg,
            pitch_deg,
            yaw_deg,
            height_m,
            show_progress,
        )

    # =================================================================
    # Internal helpers
    # =================================================================

    @staticmethod
    def _is_success(result):
        """Return True when execute() returned a final successful progress object."""
        return result is not None and bool(getattr(result, "success", False))

    def _pose_motion(
        self, motion_id, duration, roll_deg, pitch_deg, yaw_deg, height_m, show_progress
    ):
        """Internal: execute a composite pose motion (dynamic_pose/static_pose)."""
        duration = clamp_pose_duration(duration)
        roll_deg = clamp_balance_value(roll_deg, "roll")
        pitch_deg = clamp_balance_value(pitch_deg, "pitch")
        yaw_deg = clamp_balance_value(yaw_deg, "yaw")
        yaw_deg = -yaw_deg
        height_m = clamp_balance_value(height_m, "height")
        return self.execute(
            "balance_stand",
            (
                motion_id,
                {
                    "roll": roll_deg,
                    "pitch": pitch_deg,
                    "yaw": yaw_deg,
                    "height": height_m,
                    "duration": duration,
                },
            ),
            show_progress=show_progress,
        )

    @staticmethod
    def _validate_non_negative_duration(duration, name):
        value = float(duration)
        if value < 0.0:
            raise ValueError(f"{name} must be >= 0, got {duration}")
        return value

    def _validate_dance_duration(self, duration):
        value = float(duration)
        if value < MIN_DANCE_SECONDS or value > MAX_DANCE_SECONDS:
            raise ValueError(
                f"dance duration must be in [{MIN_DANCE_SECONDS}, {MAX_DANCE_SECONDS}] seconds, got {duration}"
            )
        return value

    def _set_state_with_delay(self, state_name: str, delay_seconds: float, show_progress=True):
        """Execute a state switch and sleep delay_seconds only if successful."""
        res = self.set_target_state(state_name, show_progress=show_progress)
        if self._is_success(res):
            time.sleep(delay_seconds)
        return res

    # =================================================================
    # Camera video streaming (robot.video)
    # =================================================================

    @property
    def video(self):
        """Camera video streaming (``robot.video``).

        Independent of motion control: video goes over RTSP, not through the gRPC
        channel, so big media packets never hold up your motion commands. The
        object is created on first use, so programs that do not use the camera
        pay nothing for it.

        The SDK only switches the stream on and watches it: ``open()`` blocks
        until data is really flowing and returns an RTSP address; pulling,
        decoding and muxing are up to your own player.

        Usage::

            uri = robot.video.open(CameraId.FRONT_RGB)   # blocks until data flows
            # open uri with OpenCV / ffmpeg / VLC
            robot.video.close(CameraId.FRONT_RGB)
        """
        if self._video_manager is None:
            from .video import VideoStreamManager

            self._video_manager = VideoStreamManager(self._host)
        return self._video_manager

    def close(self):
        if self._video_manager is not None:
            self._video_manager.close_all()
            self._video_manager = None
        self.channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def enable_safety_ready(self):
        """Enable automatic ready() on Ctrl+C.

        When Ctrl+C is pressed, the current motion is cancelled and
        the robot transitions to ready before the process exits.
        """
        self._safety_triggered = False

        def _cleanup():
            if not self._safety_triggered:
                return
            try:
                self.ready(show_progress=False)
            except Exception:
                pass

        atexit.register(_cleanup)

        def _handler(sig, frame):
            self._safety_triggered = True
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            sys.exit(130)

        signal.signal(signal.SIGINT, _handler)
