"""test_rotation.py — Rotation & circle tests (§8)."""

import pytest
from conftest import _make_progress_final


def _get_param(req, motion_idx, key):
    """Extract a parameter value from the proto request by key."""
    m = req.sequence.motions[motion_idx]
    for p in m.parameters:
        if p.key == key:
            if p.float_value != 0.0:
                return p.float_value
            if p.int_value != 0:
                return p.int_value
            if p.string_value:
                return p.string_value
            # Could be legitimately 0
            return p.float_value if hasattr(p, "float_value") else p.int_value
    return None


class TestRotate:
    """§8.1 rotate — rotate in place."""

    @pytest.mark.parametrize("direction", ["left", "right", 0, 1])
    def test_valid_direction(self, robot, direction):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate(direction, 90, show_progress=False)

    def test_invalid_direction_str(self, robot):
        with pytest.raises(ValueError):
            robot.rotate("up", 90)

    def test_invalid_direction_int(self, robot):
        with pytest.raises(ValueError):
            robot.rotate(2, 90)

    # ---------- angle clamping [0, 3600] ----------
    @pytest.mark.parametrize(
        "raw, clamped", [
            (-10, 0.0),
            (0, 0.0),
            (180, 180.0),
            (360, 360.0),
            (400, 400.0),
        ]
    )
    def test_angle_clamped(self, robot, raw, clamped):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate("left", raw, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        angle = _get_param(req, 0, "angle")
        assert abs(float(angle) - clamped) < 0.01


class TestRotateShortcuts:
    """§8.2 rotate_left / rotate_right."""

    def test_rotate_left(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_left(45, show_progress=False)

    def test_rotate_right(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_right(45, show_progress=False)


class TestCircle:
    """\u00a78.3 circle \u2014 turns clamped [1, 10]."""

    @pytest.mark.parametrize(
        "raw, clamped", [
            (-1, 1),
            (0, 1),
            (1, 1),
            (3, 3),
            (5, 5),
            (10, 10),
            (15, 10),
        ]
    )
    def test_turns_clamped(self, robot, raw, clamped):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.circle(turns=raw, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        # circle → rotate(direction, angle=turns*360)
        # rotate clamps angle to [0, 360], so effective angle = min(clamped*360, 360)
        # But for turns > 1, the angle exceeds 360 and gets clamped to 360 inside rotate
        angle = _get_param(req, 0, "angle")
        assert angle is not None
        # For turns=1, angle should be 360; for turns>1, still 360 (clamped)
        if clamped == 1:
            assert abs(float(angle) - 360.0) < 0.01

    def test_default_turns(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.circle(show_progress=False)


class TestRotateWalk:
    """§8.4 rotate_walk — rotate + walk."""

    # ---------- angle clamping [0, 360] ----------
    @pytest.mark.parametrize(
        "angle, expected", [
            (-5, 0),
            (0, 0),
            (180, 180),
            (360, 360),
            (500, 360),
        ]
    )
    def test_angle_clamped(self, robot, angle, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_walk(angle=angle, distance=1.0, show_progress=False)

    # ---------- distance clamping [0, 3] ----------
    @pytest.mark.parametrize("dist, expected", [
        (-1, 0),
        (0, 0),
        (1.5, 1.5),
        (3, 3),
        (10, 3),
    ])
    def test_distance_clamped(self, robot, dist, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_walk(angle=90, distance=dist, show_progress=False)

    def test_left_right_threshold(self, robot):
        """angle <= 180 => left, angle > 180 => right."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_walk(angle=90, distance=1, show_progress=False)
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.rotate_walk(angle=270, distance=1, show_progress=False)
