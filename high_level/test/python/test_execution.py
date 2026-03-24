"""test_execution.py — Execute & Sequence tests (§4, §6 velocity_sequence)."""

import sys
import os
import pytest
from conftest import _make_progress_final

# Import RobotClient for static method tests
_py_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "python"))
sys.path.insert(0, _py_root)
from dobot_quad import RobotClient


class TestExecute:
    """§4 execute — generic motion execution."""

    def test_single_motion_string(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.execute("balance_stand", show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "balance_stand"

    def test_motion_with_params_tuple(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.execute(("balance_stand", {"speed": 0.5}), show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "balance_stand"
        assert req.sequence.motions[0].parameters[0].key == "speed"

    def test_multiple_motions(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.execute("stand_up", "balance_stand", show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        ids = [m.motion_id for m in req.sequence.motions]
        assert ids == ["stand_up", "balance_stand"]

    def test_progress_success(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True, "done")])
        result = robot.execute("stand_up", show_progress=False)
        assert result is not None

    def test_progress_failure(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(False, "failed")]
        )
        result = robot.execute("stand_up", show_progress=False)
        assert result is not None


class TestMakeVelocityString:
    """§6.1 make_velocity_string — static method, list of tuples → string."""

    def test_single_step(self):
        s = RobotClient.make_velocity_string([(0.5, 0.0, 0.0, 2.0)])
        assert "0.5" in s
        assert "2.0" in s
        assert s.endswith(";")

    def test_multiple_steps(self):
        s = RobotClient.make_velocity_string([
            (0.5, 0.0, 0.0, 2.0),
            (0.0, 0.3, 0.0, 1.0),
        ])
        assert s.count(";") == 2

    def test_format(self):
        s = RobotClient.make_velocity_string([(1.0, 2.0, 3.0, 4.0)])
        assert s == "1.0,2.0,3.0,4.0;"


class TestVelocitySequence:
    """§6.2 velocity_sequence — list of velocity steps."""

    def test_single_step(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_multiple_steps(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0), (0.0, 0.3, 0.0, 1.0)], show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_stand_down_after_true(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], stand_down_after=True, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        ids = [m.motion_id for m in req.sequence.motions]
        assert "stand_down" in ids

    def test_stand_down_after_false(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], stand_down_after=False, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        ids = [m.motion_id for m in req.sequence.motions]
        assert "stand_down" not in ids

    def test_gait_walk(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], gait="walk", show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "walk_velocity_seq"

    def test_gait_flying_trot(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], gait="flying_trot", show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "flying_trot_velocity_seq"

    def test_gait_rl_raises(self, robot):
        """rl is no longer a valid gait — should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown gait"):
            robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], gait="rl", show_progress=False)

    def test_gait_invalid_raises(self, robot):
        """Completely invalid gait name should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown gait"):
            robot.velocity_sequence([(0.5, 0.0, 0.0, 2.0)], gait="sprint", show_progress=False)
