"""test_query.py — Query API tests (§2)."""

from unittest.mock import MagicMock


class TestGetState:
    """§2.1 get_state."""

    def test_returns_response(self, robot):
        res = robot.get_state()
        assert res.success is True

    def test_response_has_robot_state(self, robot):
        res = robot.get_state()
        assert hasattr(res, "robot_state")
        assert len(res.robot_state.pos_body) == 3

    def test_response_has_current_state(self, robot):
        res = robot.get_state()
        assert isinstance(res.current_state, str)

    def test_response_has_speed_ratio(self, robot):
        res = robot.get_state()
        assert isinstance(res.current_speed_ratio, int)

    def test_response_has_obstacle_avoidance(self, robot):
        res = robot.get_state()
        assert isinstance(res.obstacle_avoidance_enabled, bool)

    def test_robot_state_has_leg_fields(self, robot):
        """RobotState should have leg fields (arm fields were removed)."""
        rs = robot.get_state().robot_state
        assert hasattr(rs, "jpos_leg")
        assert hasattr(rs, "jvel_leg")
        assert hasattr(rs, "jtau_leg")


class TestGetMotions:
    """§2.2 get_motions."""

    def test_returns_response(self, robot):
        res = robot.get_motions()
        assert res.success is True

    def test_calls_stub(self, robot):
        robot.get_motions()
        robot._mock_stub.GetAvailableMotions.assert_called_once()


class TestGetCurrentStateName:
    """§2.3 get_current_state_name."""

    def test_returns_string(self, robot):
        name = robot.get_current_state_name()
        assert isinstance(name, str)
        assert name == "passive"  # from mock default

    def test_returns_empty_on_failure(self, robot):
        robot._mock_stub.GetRobotState.return_value = MagicMock(
            success=False, current_state="whatever"
        )
        assert robot.get_current_state_name() == ""


class TestGetSpeedRatio:
    """§2.4 get_speed_ratio."""

    def test_returns_int(self, robot):
        ratio = robot.get_speed_ratio()
        assert isinstance(ratio, int)
        assert ratio == 50  # from mock default

    def test_returns_set_value(self, robot):
        robot._mock_stub.SetSpeedRatio.return_value = MagicMock(
            success=True, current_speed_ratio=75
        )
        robot.set_speed_ratio(75)
        assert robot.get_speed_ratio() == 75


class TestGetObstacleAvoidance:
    """§2.5 get_obstacle_avoidance."""

    def test_returns_bool(self, robot):
        result = robot.get_obstacle_avoidance()
        assert isinstance(result, bool)

    def test_returns_set_value(self, robot):
        robot._mock_stub.SetObstacleAvoidance.return_value = MagicMock(
            success=True, current_enabled=False
        )
        robot.set_obstacle_avoidance(False)
        assert robot.get_obstacle_avoidance() is False
