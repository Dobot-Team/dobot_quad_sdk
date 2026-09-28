"""test_constructor.py — Constructor and context manager tests."""

from unittest.mock import patch, MagicMock


class TestConstructor:
    """§1 Constructor / Connection."""

    def test_constructor_seeds_obstacle_avoidance_enabled(self, robot):
        """Constructor seeds obstacle avoidance as enabled locally (no RPC)."""
        assert robot._obstacle_avoidance is True
        robot._mock_stub.SetObstacleAvoidance.assert_not_called()

    def test_context_manager(self, robot):
        """with statement should call close() on exit."""
        with robot as r:
            assert r is robot
        robot.channel.close.assert_called_once()

    def test_close(self, robot):
        robot.close()
        robot.channel.close.assert_called_once()

    def test_led_cache_initialized_empty(self, robot):
        assert robot._led_cache == {}
