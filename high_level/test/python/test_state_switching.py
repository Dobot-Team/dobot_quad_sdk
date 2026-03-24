"""test_state_switching.py — State switching tests (§5).

Changes vs. previous version:
  - State methods no longer have set_ prefix (walk, not set_walk).
  - stand_up removed; replaced by emergency + ready.
  - toggle_legs/x_leg removed; replaced by change_mode.
  - set_target_state validates state names (case-insensitive).
"""

import pytest
from unittest.mock import call
from conftest import _make_progress_final


class TestSetTargetState:
    """§5.1 set_target_state — generic state switch with validation."""

    def test_calls_execute(self, robot):
        """set_target_state should call execute with the state name."""
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.set_target_state("balance_stand")
        robot._mock_stub.ExecuteSequence.assert_called()
        robot._mock_sleep.assert_not_called()

    def test_case_insensitive(self, robot):
        """State names should be case-insensitive."""
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.set_target_state("Balance_Stand")
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "balance_stand"

    def test_case_insensitive_upper(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.set_target_state("WALK")
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == "walk"

    def test_invalid_state_raises(self, robot):
        with pytest.raises(ValueError, match="Unknown state"):
            robot.set_target_state("some_custom_state")

    @pytest.mark.parametrize("bad_state", [
        "x_legs",
        "invalid",
        "run",
        "",
        "  ",
    ])
    def test_various_invalid_states(self, robot, bad_state):
        with pytest.raises(ValueError):
            robot.set_target_state(bad_state)


class TestPredefinedStates:
    """§5.2 Predefined states — NO set_ prefix, verify correct motion_id."""

    @pytest.mark.parametrize("method, expected_id", [
        ("passive", "passive"),
        ("emergency", "passive"),
        ("ready", "ready"),
        ("stand_down", "stand_down"),
        ("balance_stand", "balance_stand"),
        ("walk", "walk"),
        ("flying_trot", "flying_trot"),
        ("dance0", "dance0"),
        ("wave", "wave"),
        ("jump", "jump"),
        ("backflip", "backflip"),
        ("recovery", "recovery"),
    ])
    def test_method_sends_correct_motion_id(self, robot, method, expected_id):
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        getattr(robot, method)(show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == expected_id

    @pytest.mark.parametrize("alias, expected_id", [
        ("dance", "dance0"),
        ("wave_hand", "wave"),
    ])
    def test_block_aliases(self, robot, alias, expected_id):
        """Block aliases delegate to the correct state method."""
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        getattr(robot, alias)(show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        assert req.sequence.motions[0].motion_id == expected_id


class TestRemovedMethods:
    """§5 Verify that removed methods do NOT exist on RobotClient."""

    @pytest.mark.parametrize("name", [
        "set_passive",
        "set_stand_down",
        "set_stand_up",
        "set_balance_stand",
        "set_walk",
        "set_flying_trot",
        "set_rl",
        "set_dance0",
        "set_wave",
        "set_jump",
        "set_backflip",
        "set_recovery",
        "set_x_legs",
    ])
    def test_set_methods_removed(self, robot, name):
        """set_xxx methods and rl should not exist."""
        # RobotClient is a real object (not MagicMock), so hasattr is reliable.
        assert not hasattr(robot, name), f"{name} should not exist"


class TestChangeMode:
    """§5.3 change_mode — switch knee configuration."""

    def test_change_mode_sends_change_mode(self, robot):
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.change_mode(show_progress=False)
        req = robot._mock_stub.ExecuteSequence.call_args.args[0]
        ids = [m.motion_id for m in req.sequence.motions]
        assert ids == ["change_mode"]


class TestRemovedLegMethods:
    """§5.4 Verify toggle_legs, x_leg, stand_up are removed."""

    @pytest.mark.parametrize("name", ["toggle_legs", "x_leg", "stand_up"])
    def test_removed_methods(self, robot, name):
        assert not hasattr(robot, name), f"{name} should not exist"


class TestStatePostSleep:
    """State wrapper post-sleep behavior after successful execution."""

    @pytest.mark.parametrize("method_name, expected", [
        ("stand_down", 2.0),
        ("balance_stand", 2.0),
        ("jump", 3.0),
        ("recovery", 4.0),
    ])
    def test_wrapper_sleep_seconds(self, robot, method_name, expected):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        getattr(robot, method_name)(show_progress=False)
        robot._mock_sleep.assert_called_once_with(expected)

    def test_failed_wrapper_does_not_sleep(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(False)])
        robot.stand_down(show_progress=False)
        robot._mock_sleep.assert_not_called()


class TestDanceConfigurableDuration:
    """dance / dance0 support configurable duration with constraints [1, 14]."""

    def test_dance_default_13_seconds(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.dance(show_progress=False)
        robot._mock_sleep.assert_called_once_with(13.0)

    def test_dance_custom_duration(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.return_value = iter(
            [_make_progress_final(True)])
        robot.dance(5, show_progress=False)
        robot._mock_sleep.assert_called_once_with(5.0)

    @pytest.mark.parametrize("bad_duration", [0, 0.5, 14.5, 20, -1])
    def test_dance_invalid_duration_raises(self, robot, bad_duration):
        with pytest.raises(ValueError, match="dance duration must be in"):
            robot.dance(bad_duration, show_progress=False)


class TestWaveSpecialFlow:
    """wave(): configurable first delay, second fixed delay (2s)."""

    def test_wave_runs_twice_and_default_sleep_pattern(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.side_effect = [
            iter([_make_progress_final(True)]),
            iter([_make_progress_final(True)]),
        ]

        robot.wave(show_progress=False)

        assert robot._mock_stub.ExecuteSequence.call_count == 2
        assert robot._mock_sleep.call_args_list == [call(5.0), call(2.0)]

    def test_wave_custom_first_duration(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.side_effect = [
            iter([_make_progress_final(True)]),
            iter([_make_progress_final(True)]),
        ]

        robot.wave(20, show_progress=False)

        assert robot._mock_sleep.call_args_list == [call(20.0), call(2.0)]

    def test_wave_first_failure_stops_flow(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.side_effect = [
            iter([_make_progress_final(False)]),
            iter([_make_progress_final(True)]),
        ]

        robot.wave(show_progress=False)

        assert robot._mock_stub.ExecuteSequence.call_count == 1
        robot._mock_sleep.assert_not_called()

    def test_wave_second_failure_no_final_sleep_2(self, robot):
        robot._mock_sleep.reset_mock()
        robot._mock_stub.ExecuteSequence.side_effect = [
            iter([_make_progress_final(True)]),
            iter([_make_progress_final(False)]),
        ]

        robot.wave(show_progress=False)

        assert robot._mock_stub.ExecuteSequence.call_count == 2
        assert robot._mock_sleep.call_args_list == [call(5.0)]

    def test_wave_negative_duration_raises(self, robot):
        with pytest.raises(ValueError, match="wave duration must be >= 0"):
            robot.wave(-1, show_progress=False)
