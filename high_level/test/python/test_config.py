"""test_config.py — Configuration API tests (§3)."""

import pytest
from unittest.mock import MagicMock


class TestSetSpeedRatio:
    """§3.1 set_speed_ratio — clamping [10, 100]."""

    def test_normal_value(self, robot):
        robot._mock_stub.SetSpeedRatio.return_value = MagicMock(
            success=True, current_speed_ratio=50)
        resp = robot.set_speed_ratio(50)
        sent = robot._mock_stub.SetSpeedRatio.call_args.args[0]
        assert sent.speed_ratio == 50

    @pytest.mark.parametrize("input_val, expected", [
        (-10, 10),
        (-1, 10),
        (0, 10),
        (1, 10),
        (9, 10),
        (10, 10),
        (50, 50),
        (100, 100),
        (101, 100),
        (999, 100),
    ])
    def test_clamping(self, robot, input_val, expected):
        """Values outside [10, 100] are silently clamped."""
        robot.set_speed_ratio(input_val)
        sent = robot._mock_stub.SetSpeedRatio.call_args.args[0]
        assert sent.speed_ratio == expected

    def test_returns_response(self, robot):
        resp = robot.set_speed_ratio(60)
        assert hasattr(resp, "current_speed_ratio")


class TestSetObstacleAvoidance:
    """§3.2 set_obstacle_avoidance."""

    def test_bool_true(self, robot):
        robot.set_obstacle_avoidance(True)
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is True

    def test_bool_false(self, robot):
        robot.set_obstacle_avoidance(False)
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is False

    def test_string_on(self, robot):
        robot.set_obstacle_avoidance("on")
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is True

    def test_string_off(self, robot):
        robot.set_obstacle_avoidance("off")
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is False

    def test_string_case_insensitive(self, robot):
        robot.set_obstacle_avoidance("ON")
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is True

    def test_string_whitespace(self, robot):
        robot.set_obstacle_avoidance("  Off  ")
        sent = robot._mock_stub.SetObstacleAvoidance.call_args.args[0]
        assert sent.enable is False

    @pytest.mark.parametrize("bad_input", [
        "yes",
        "no",
        "true",
        "false",
        "1",
        "0",
        "enable",
        "disable",
        "",
    ])
    def test_invalid_string_raises_valueerror(self, robot, bad_input):
        with pytest.raises(ValueError):
            robot.set_obstacle_avoidance(bad_input)
