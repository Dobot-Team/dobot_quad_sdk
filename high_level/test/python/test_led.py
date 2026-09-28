"""test_led.py — LED control API tests."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def led():
    """Leg, Color, LegLedConfig — imported lazily via robot fixture's import path."""
    from dobot_quad.robot_client import Leg, Color, LegLedConfig
    return Leg, Color, LegLedConfig


def _cmd_by_leg(req, leg):
    for cmd in req.commands:
        if cmd.leg == leg:
            return cmd
    raise AssertionError(f"leg {leg} not found in {len(req.commands)} commands")


def _assert_four_main_legs(req, Leg):
    assert len(req.commands) == 4
    assert [cmd.leg for cmd in req.commands] == [Leg.FL, Leg.FR, Leg.RL, Leg.RR]


def _scale(r, g, b, bri):
    from dobot_quad.robot_client import _scale_rgb_by_brightness
    return _scale_rgb_by_brightness(r, g, b, bri)


class TestScaleRgbByBrightness:
    def test_full_brightness_unchanged(self):
        assert _scale(255, 128, 64, 255) == (255, 128, 64)

    def test_zero_brightness(self):
        assert _scale(255, 128, 64, 0) == (0, 0, 0)

    def test_half_brightness(self):
        assert _scale(255, 0, 0, 128) == (128, 0, 0)
        assert _scale(255, 0, 0, 32) == (32, 0, 0)


class TestSetLegsRgb:
    """Batch RGB + brightness via SetLeds RPC."""

    def test_empty_configs_returns_true_without_rpc(self, robot, led):
        assert robot.set_legs_rgb([]) is True
        robot._mock_stub.SetLeds.assert_not_called()

    def test_single_leg_pads_others_off(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=128)])
        req = robot._mock_stub.SetLeds.call_args.args[0]
        _assert_four_main_legs(req, Leg)

        fl = _cmd_by_leg(req, Leg.FL)
        assert (fl.r, fl.g, fl.b) == _scale(255, 0, 0, 128)
        assert fl.brightness == 255  # wire brightness always full
        assert robot._led_cache[Leg.FL] == (128, 255, 0, 0)  # logical cache
        for leg in (Leg.FR, Leg.RL, Leg.RR):
            cmd = _cmd_by_leg(req, leg)
            assert (cmd.r, cmd.g, cmd.b) == (0, 0, 0)
            assert cmd.brightness == 255

    def test_multiple_legs_pads_to_four(self, robot, led):
        Leg, Color, LegLedConfig = led
        configs = [
            LegLedConfig(leg=Leg.FL, r=255, g=0, b=0),
            LegLedConfig(leg=Leg.FR, r=0, g=255, b=0),
        ]
        robot.set_legs_rgb(configs)
        req = robot._mock_stub.SetLeds.call_args.args[0]
        _assert_four_main_legs(req, Leg)
        assert (_cmd_by_leg(req, Leg.FL).r,
                _cmd_by_leg(req, Leg.FL).g,
                _cmd_by_leg(req, Leg.FL).b) == (255, 0, 0)
        assert (_cmd_by_leg(req, Leg.FR).r,
                _cmd_by_leg(req, Leg.FR).g,
                _cmd_by_leg(req, Leg.FR).b) == (0, 255, 0)
        assert (_cmd_by_leg(req, Leg.RL).r,
                _cmd_by_leg(req, Leg.RL).g,
                _cmd_by_leg(req, Leg.RL).b) == (0, 0, 0)
        robot._mock_stub.SetLeds.assert_called_once()

    def test_cache_resent_on_incremental_set(self, robot, led):
        """Previously lit legs are resent from cache, not force-cleared."""
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=200)])
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FR, r=0, g=255, b=0, brightness=180)])
        req = robot._mock_stub.SetLeds.call_args.args[0]
        _assert_four_main_legs(req, Leg)
        fl = _cmd_by_leg(req, Leg.FL)
        assert (fl.r, fl.g, fl.b) == _scale(255, 0, 0, 200)
        assert fl.brightness == 255
        fr = _cmd_by_leg(req, Leg.FR)
        assert (fr.r, fr.g, fr.b) == _scale(0, 255, 0, 180)
        assert fr.brightness == 255

    @pytest.mark.parametrize("input_brightness, expected_bri", [
        (300, 255),
        (128, 128),
    ])
    def test_brightness_clamping(self, robot, led, input_brightness, expected_bri):
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=10, g=20, b=30,
                                        brightness=input_brightness)])
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == _scale(10, 20, 30, expected_bri)
        assert robot._led_cache[Leg.FL][0] == expected_bri

    def test_negative_brightness_uses_default(self, robot, led):
        """brightness < 0 is treated as 'keep cache/default', not clamped."""
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=10, g=20, b=30, brightness=-5)])
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == (10, 20, 30)

    def test_default_brightness_fallback(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb(
            [LegLedConfig(leg=Leg.FL, r=1, g=2, b=3)],
            default_brightness=64,
        )
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == _scale(1, 2, 3, 64)
        assert robot._led_cache[Leg.FL] == (64, 1, 2, 3)

    def test_no_cache_defaults_to_255(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.RL, r=0, g=0, b=255)])
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.RL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == (0, 0, 255)

    def test_uses_cached_brightness(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.FL] = (80, 100, 50, 25)
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=255, g=0, b=0)])
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == _scale(255, 0, 0, 80)
        assert robot._led_cache[Leg.FL] == (80, 255, 0, 0)

    def test_updates_cache_for_all_main_legs(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_legs_rgb([LegLedConfig(leg=Leg.FR, r=1, g=2, b=3, brightness=50)])
        assert robot._led_cache[Leg.FR] == (50, 1, 2, 3)
        assert robot._led_cache[Leg.FL] == (255, 0, 0, 0)
        assert robot._led_cache[Leg.RL] == (255, 0, 0, 0)
        assert robot._led_cache[Leg.RR] == (255, 0, 0, 0)

    def test_rejected_returns_false(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._mock_stub.SetLeds.return_value = MagicMock(
            accepted=False, message="busy")
        assert robot.set_legs_rgb(
            [LegLedConfig(leg=Leg.FL, r=255, g=0, b=0)]) is False


class TestSetLegRgb:
    def test_delegates_to_set_legs_rgb(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_leg_rgb(Leg.FL, 255, 128, 64, brightness=200)
        req = robot._mock_stub.SetLeds.call_args.args[0]
        _assert_four_main_legs(req, Leg)
        cmd = _cmd_by_leg(req, Leg.FL)
        assert (cmd.r, cmd.g, cmd.b) == _scale(255, 128, 64, 200)
        assert cmd.brightness == 255
        assert robot._led_cache[Leg.FL] == (200, 255, 128, 64)


class TestSetLegColor:
    @pytest.mark.parametrize("color_name, expected_rgb", [
        ("RED", (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE", (0, 0, 255)),
        ("WHITE", (255, 255, 255)),
        ("OFF", (0, 0, 0)),
    ])
    def test_predefined_colors(self, robot, led, color_name, expected_rgb):
        Leg, Color, LegLedConfig = led
        color = getattr(Color, color_name)
        robot.set_leg_color(Leg.FL, color)
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert (cmd.r, cmd.g, cmd.b) == expected_rgb


class TestSetLegBrightness:
    def test_preserves_cached_rgb(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.RL] = (100, 10, 20, 30)
        robot.set_leg_brightness(Leg.RL, 50)
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.RL)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == _scale(10, 20, 30, 50)
        assert robot._led_cache[Leg.RL] == (50, 10, 20, 30)

    def test_no_cache_defaults_white(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_leg_brightness(Leg.RR, 128)
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.RR)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == _scale(255, 255, 255, 128)


class TestSetAllLegs:
    def test_four_legs_one_rpc(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_all_legs_rgb(255, 0, 0, brightness=200)
        req = robot._mock_stub.SetLeds.call_args.args[0]
        _assert_four_main_legs(req, Leg)
        wired = _scale(255, 0, 0, 200)
        for cmd in req.commands:
            assert (cmd.r, cmd.g, cmd.b) == wired
            assert cmd.brightness == 255

    def test_all_legs_color(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.set_all_legs_color(Color.CYAN, brightness=100)
        req = robot._mock_stub.SetLeds.call_args.args[0]
        assert len(req.commands) == 4
        wired = _scale(0, 255, 255, 100)
        for cmd in req.commands:
            assert (cmd.r, cmd.g, cmd.b) == wired
            assert cmd.brightness == 255


class TestTurnOffLeg:
    def test_rgb_zero_preserves_brightness(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.FL] = (180, 255, 100, 50)
        robot.turn_off_leg(Leg.FL)
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FL)
        assert cmd.r == 0 and cmd.g == 0 and cmd.b == 0
        assert cmd.brightness == 255
        assert robot._led_cache[Leg.FL] == (180, 0, 0, 0)

    def test_no_cache_uses_default_brightness(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot.turn_off_leg(Leg.FR)
        cmd = _cmd_by_leg(robot._mock_stub.SetLeds.call_args.args[0], Leg.FR)
        assert cmd.brightness == 255
        assert (cmd.r, cmd.g, cmd.b) == (0, 0, 0)


class TestResetLegs:
    def test_reset_specific_legs(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.FL] = (255, 1, 2, 3)
        robot._led_cache[Leg.FR] = (255, 4, 5, 6)
        robot.reset_legs([Leg.FL])
        req = robot._mock_stub.ResetLeds.call_args.args[0]
        assert list(req.legs) == [Leg.FL]
        assert Leg.FL not in robot._led_cache
        assert Leg.FR in robot._led_cache

    def test_reset_all_clears_cache(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.FL] = (255, 1, 2, 3)
        robot._led_cache[Leg.RR] = (128, 4, 5, 6)
        robot.reset_legs()
        req = robot._mock_stub.ResetLeds.call_args.args[0]
        assert len(req.legs) == 0
        assert robot._led_cache == {}

    def test_rejected_preserves_cache(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._led_cache[Leg.FL] = (255, 1, 2, 3)
        robot._mock_stub.ResetLeds.return_value = MagicMock(
            accepted=False, message="error")
        assert robot.reset_legs([Leg.FL]) is False
        assert Leg.FL in robot._led_cache


class TestLedValidation:
    @pytest.mark.parametrize("r, g, b", [
        (-1, 0, 0),
        (0, 256, 0),
        (0, 0, 300),
    ])
    def test_invalid_rgb_raises(self, robot, led, r, g, b):
        Leg, Color, LegLedConfig = led
        with pytest.raises(ValueError, match="RGB values must be 0-255"):
            robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=r, g=g, b=b)])

    @pytest.mark.parametrize("fill_leg_name", ["FILL_FRONT", "FILL_BACK"])
    def test_fill_light_rejected(self, robot, led, fill_leg_name):
        Leg, Color, LegLedConfig = led
        fill_leg = getattr(Leg, fill_leg_name)
        with pytest.raises(ValueError, match="Leg LED set APIs only support"):
            robot.set_leg_rgb(fill_leg, 255, 0, 0)
        with pytest.raises(ValueError, match="Leg LED set APIs only support"):
            robot.set_legs_rgb([LegLedConfig(leg=fill_leg, r=255, g=0, b=0)])
        robot._mock_stub.SetLeds.assert_not_called()


class TestLedRpcErrors:
    @staticmethod
    def _make_rpc_error():
        import dobot_quad.robot_client as rc

        class FakeRpcError(rc.grpc.RpcError):
            def code(self):
                status = MagicMock()
                status.name = "UNAVAILABLE"
                return status

            def details(self):
                return "service unavailable"

        return FakeRpcError()

    def test_set_leds_grpc_error(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._mock_stub.SetLeds.side_effect = self._make_rpc_error()
        assert robot.set_leg_rgb(Leg.FL, 255, 0, 0) is False

    def test_reset_leds_grpc_error(self, robot, led):
        Leg, Color, LegLedConfig = led
        robot._mock_stub.ResetLeds.side_effect = self._make_rpc_error()
        assert robot.reset_legs([Leg.FL]) is False
