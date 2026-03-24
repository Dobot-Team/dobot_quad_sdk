"""test_balance.py — Balance & Dynamic Pose tests (§9, §10).

Covers:
  - Individual balance methods (value clamped per axis, duration clamped [0.5, 10])
  - balance_sequence (motion_id validation, value clamping)
  - _balance_motion validation
  - dynamic_pose (duration clamped [0.5, 10]s, value per axis)
  - dance alias
"""

import pytest
from conftest import _make_progress_final


class TestBalanceMotions:
    """§9.1 Individual balance methods."""

    @pytest.mark.parametrize(
        "method",
        [
            "balance_pitch",
            "balance_yaw",
            "balance_roll",
            "balance_height",
        ],
    )
    def test_each_balance_method(self, robot, method):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        kwargs = {"value": 10.0, "duration": 2.0, "mode": "dynamic"}
        if method == "balance_height":
            kwargs["value"] = -0.05
        getattr(robot, method)(**kwargs, show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_balance_neutral(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_neutral(duration=0.5, show_progress=False)

    def test_balance_stand_prepended(self, robot):
        """balance_stand should be the first motion in the sequence."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_pitch(value=10.0, duration=2.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "balance_stand"
        assert req.sequence.motions[1].motion_id == "balance_pitch"


class TestBalanceMotionValidation:
    """§9 _balance_motion — motion_id validation + value clamping."""

    def test_invalid_motion_id_raises(self, robot):
        with pytest.raises(ValueError, match="Unknown balance motion"):
            robot._balance_motion("invalid_motion", 0.5, 1.0, "dynamic", False)

    @pytest.mark.parametrize(
        "bad_id",
        [
            "walk",
            "stand_up",
            "pitch",
            "balance_invalid",
            "",
        ],
    )
    def test_various_invalid_motion_ids(self, robot, bad_id):
        with pytest.raises(ValueError):
            robot._balance_motion(bad_id, 0.5, 1.0, "dynamic", False)

    # ---------- value clamping for pitch (degrees) ----------
    @pytest.mark.parametrize(
        "val_in, expected",
        [
            (-50.0, -15.0),
            (-15.0, -15.0),
            (-10.0, -10.0),
            (0.0, 0.0),
            (15.0, 15.0),
            (20.0, 15.0),
            (50.0, 15.0),
        ],
    )
    def test_pitch_value_clamped(self, robot, val_in, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_pitch(value=val_in, duration=2.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        pitch_motion = req.sequence.motions[1]
        assert pitch_motion.motion_id == "balance_pitch"
        val_param = None
        for p in pitch_motion.parameters:
            if p.key == "value":
                val_param = p.float_value
        assert val_param is not None
        assert abs(val_param - expected) < 0.01

    # ---------- value clamping for height (meters, only downward) ----------
    @pytest.mark.parametrize(
        "val_in, expected",
        [
            (-0.20, -0.12),
            (-0.12, -0.12),
            (-0.05, -0.05),
            (0.0, 0.0),
            (0.05, 0.0),
        ],
    )
    def test_height_value_clamped(self, robot, val_in, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_height(value=val_in, duration=2.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        height_motion = req.sequence.motions[1]
        assert height_motion.motion_id == "balance_height"
        val_param = None
        for p in height_motion.parameters:
            if p.key == "value":
                val_param = p.float_value
        assert val_param is not None
        assert abs(val_param - expected) < 0.01


class TestBalanceSequence:
    """§9.2 balance_sequence — batch balance motions (tuple format)."""

    def test_single_motion(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_sequence(
            [("balance_pitch", 10.0, 2.0, "dynamic")],
            show_progress=False,
        )
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_multiple_motions(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_sequence(
            [
                ("balance_pitch", 10.0, 2.0, "dynamic"),
                ("balance_yaw", 15.0, 1.0, "static"),
                ("balance_neutral", 0.0, 0.5, "dynamic"),
            ],
            show_progress=False,
        )
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        # balance_stand + 3 motions = 4
        assert len(req.sequence.motions) == 4

    def test_balance_stand_is_first(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_sequence(
            [("balance_pitch", 10.0, 2.0, "dynamic")],
            show_progress=False,
        )
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "balance_stand"

    def test_invalid_motion_id_raises(self, robot):
        with pytest.raises(ValueError, match="Unknown balance motion"):
            robot.balance_sequence(
                [("invalid_motion", 10.0, 1.0, "dynamic")],
                show_progress=False,
            )

    def test_mixed_valid_invalid_raises(self, robot):
        """First valid, second invalid → should raise before execute."""
        with pytest.raises(ValueError):
            robot.balance_sequence(
                [
                    ("balance_pitch", 10.0, 2.0, "dynamic"),
                    ("bad_motion", 10.0, 1.0, "dynamic"),
                ],
                show_progress=False,
            )

    # value clamping inside balance_sequence (balance_roll [-30,30])
    @pytest.mark.parametrize(
        "val_in, expected",
        [
            (-50.0, -30.0),
            (-30.0, -30.0),
            (-10.0, -10.0),
            (0.0, 0.0),
            (20.0, 20.0),
            (50.0, 30.0),
        ],
    )
    def test_value_clamped_in_sequence(self, robot, val_in, expected):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.balance_sequence(
            [("balance_roll", val_in, 1.0, "dynamic")],
            show_progress=False,
        )
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        roll_motion = req.sequence.motions[1]
        val_param = None
        for p in roll_motion.parameters:
            if p.key == "value":
                val_param = p.float_value
        assert val_param is not None
        assert abs(val_param - expected) < 0.01


class TestDynamicPose:
    """§10 dynamic_pose — multi-axis pose with value/duration/mode.

    Duration clamped to [0.5, 10]s.
    """

    def test_normal_duration(self, robot):
        """duration=2.0 within [0.5, 10]."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.dynamic_pose(duration=2.0, roll_deg=10.0, show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_dynamic_pose_parameters(self, robot):
        """dynamic_pose should pass all axis parameters to the motion."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.dynamic_pose(duration=2.0, pitch_deg=10.0, show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        # Should have balance_stand + dynamic_pose
        assert len(req.sequence.motions) == 2
        dynamic_pose_motion = req.sequence.motions[1]
        assert dynamic_pose_motion.motion_id == "dynamic_pose"
        # Check that required parameters are present
        param_keys = {p.key for p in dynamic_pose_motion.parameters}
        assert "pitch" in param_keys
        assert "duration" in param_keys

    def test_four_axes_in_sequence(self, robot):
        """dynamic_pose creates a single motion with all 4 axes as parameters."""
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.dynamic_pose(
            duration=2.0,
            roll_deg=10.0,
            pitch_deg=15.0,
            yaw_deg=5.0,
            height_m=-0.03,
            show_progress=False,
        )
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        # balance_stand + dynamic_pose = 2 motions
        assert len(req.sequence.motions) == 2
        ids = [m.motion_id for m in req.sequence.motions]
        assert ids == [
            "balance_stand",
            "dynamic_pose",
        ]
        # Check that all 4 axes are passed as parameters
        dynamic_pose_motion = req.sequence.motions[1]
        param_keys = {p.key for p in dynamic_pose_motion.parameters}
        assert "roll" in param_keys
        assert "pitch" in param_keys
        assert "yaw" in param_keys
        assert "height" in param_keys


class TestDance:
    """§10.2 dance — special motion."""

    def test_dance_executes(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.dance(show_progress=False)
        robot._mock_stub.ExecuteSequence.assert_called()

    def test_dance_sends_dance0(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
        robot.dance(show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "dance0"
