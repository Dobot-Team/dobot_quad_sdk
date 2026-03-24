"""test_locomotion.py — Locomotion tests (§7 line_walk, directional shortcuts).

Covers:
  - direction validation (int 0-3, string names, errors)
  - distance clamping [0, 3]
  - speed_ratio clamping [10, 100]
"""

import pytest
from conftest import _make_progress_final


class TestLineWalk:
    """§7.1 line_walk — direction: 0=front, 1=back, 2=left, 3=right."""

    def test_forward(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.line_walk(0, 1.0, show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    @pytest.mark.parametrize("direction", [0, 1, 2, 3])
    def test_valid_int_directions(self, robot, direction):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.line_walk(direction, 0.5, show_progress=False)

    # ---------- string direction support ----------
    @pytest.mark.parametrize(
        "name, expected_int",
        [
            ("forward", 0),
            ("front", 0),
            ("backward", 1),
            ("back", 1),
            ("left", 2),
            ("right", 3),
            ("Forward", 0),
            ("BACKWARD", 1),  # case-insensitive
        ]
    )
    def test_string_direction(self, robot, name, expected_int):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.line_walk(name, 1.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        m = req.sequence.motions[0]
        assert m.motion_id == "line_walk"
        dir_param = None
        for p in m.parameters:
            if p.key == "direction":
                dir_param = p.int_value
        assert dir_param == expected_int

    # ---------- invalid direction ----------
    @pytest.mark.parametrize("bad_dir", [4, -1, 5, 99])
    def test_invalid_int_direction_raises(self, robot, bad_dir):
        with pytest.raises(ValueError, match="direction must be"):
            robot.line_walk(bad_dir, 1.0, show_progress=False)

    @pytest.mark.parametrize("bad_dir", ["up", "down", "sideways", ""])
    def test_invalid_string_direction_raises(self, robot, bad_dir):
        with pytest.raises(ValueError, match="Unknown direction"):
            robot.line_walk(bad_dir, 1.0, show_progress=False)

    # ---------- distance clamping [0, 3] ----------
    @pytest.mark.parametrize(
        "dist_in, expected", [
            (-5.0, 0.0),
            (0.0, 0.0),
            (1.5, 1.5),
            (3.0, 3.0),
            (10.0, 3.0),
        ]
    )
    def test_distance_clamped(self, robot, dist_in, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.line_walk(0, dist_in, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        m = req.sequence.motions[0]
        dist_param = None
        for p in m.parameters:
            if p.key == "distance":
                dist_param = p.float_value
        assert dist_param is not None
        assert abs(dist_param - expected) < 0.01

    # ---------- speed_ratio clamping [10, 100] ----------
    @pytest.mark.parametrize(
        "sr_in, expected", [
            (0, 10),
            (5, 10),
            (10, 10),
            (50, 50),
            (100, 100),
            (150, 100),
        ]
    )
    def test_speed_ratio_clamped(self, robot, sr_in, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot._mock_stub.SetSpeedRatio.reset_mock()
        robot.line_walk(0, 1.0, speed_ratio=sr_in, show_progress=False)
        # First SetSpeedRatio call sets the requested (clamped) value
        calls = robot._mock_stub.SetSpeedRatio.call_args_list
        assert len(calls) >= 1
        sent_ratio = calls[0].args[0].speed_ratio
        assert sent_ratio == expected

    def test_direction_and_distance_in_proto(self, robot):
        """line_walk should pass direction and distance as parameters."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.line_walk(0, 2.5, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        m = req.sequence.motions[0]
        assert m.motion_id == "line_walk"
        params = {p.key: p for p in m.parameters}
        assert "direction" in params
        assert "distance" in params

    def test_no_speed_ratio_uses_base(self, robot):
        """line_walk without explicit speed_ratio should NOT call SetSpeedRatio."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot._mock_stub.SetSpeedRatio.reset_mock()
        robot.line_walk(0, 1.0, show_progress=False)
        # Only SetObstacleAvoidance should be called, not SetSpeedRatio
        robot._mock_stub.SetSpeedRatio.assert_not_called()

    def test_explicit_speed_ratio_saved_and_restored(self, robot):
        """line_walk with explicit speed_ratio should set then restore base."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot._mock_stub.SetSpeedRatio.reset_mock()
        robot.line_walk(0, 1.0, speed_ratio=60, show_progress=False)
        calls = robot._mock_stub.SetSpeedRatio.call_args_list
        # First call sets 60, second call restores base (50)
        assert len(calls) == 2
        assert calls[0].args[0].speed_ratio == 60
        assert calls[1].args[0].speed_ratio == 50  # restored to base


class TestDirectionalShortcuts:
    """§7.2 Directional convenience methods."""

    @pytest.mark.parametrize(
        "method", [
            "walk_forward",
            "walk_backward",
            "move_left",
            "move_right",
        ]
    )
    def test_shortcut_executes(self, robot, method):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        getattr(robot, method)(1.0, show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_walk_forward_default_distance(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.walk_forward(show_progress=False)

    def test_walk_forward_sends_direction_0(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.walk_forward(2.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        m = req.sequence.motions[0]
        assert m.motion_id == "line_walk"
        dir_param = None
        for p in m.parameters:
            if p.key == "direction":
                dir_param = p.int_value
        assert dir_param == 0

    def test_walk_backward_sends_direction_1(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.walk_backward(2.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        m = req.sequence.motions[0]
        dir_param = None
        for p in m.parameters:
            if p.key == "direction":
                dir_param = p.int_value
        assert dir_param == 1
