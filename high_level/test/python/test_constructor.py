"""test_constructor.py — Constructor and context manager tests."""

from unittest.mock import patch, MagicMock


class TestConstructor:
    """§1 Constructor / Connection."""

    def test_constructor_enables_obstacle_avoidance(self, robot):
        """Constructor enables obstacle avoidance."""
        calls = robot._mock_stub.SetObstacleAvoidance.call_args_list
        assert calls[0].args[0].enable is True

    def test_context_manager(self, robot):
        """with statement should call close() on exit."""
        with robot as r:
            assert r is robot
        robot.channel.close.assert_called_once()

    def test_close(self, robot):
        robot.close()
        robot.channel.close.assert_called_once()
