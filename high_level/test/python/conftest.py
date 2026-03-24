"""conftest.py — Shared fixtures for all robot_client tests.

Provides a fully-mocked RobotClient so every test runs offline.
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make the dobot_quad package importable (even when not pip-installed)
# ---------------------------------------------------------------------------
_py_root = os.path.join(os.path.dirname(__file__), "..", "..", "python")
_py_root = os.path.abspath(_py_root)
sys.path.insert(0, _py_root)

# ---------------------------------------------------------------------------
# Reusable mock response builders
# ---------------------------------------------------------------------------


def _make_speed_ratio_response(ratio=50):
    resp = MagicMock()
    resp.success = True
    resp.message = ""
    resp.current_speed_ratio = ratio
    return resp


def _make_obstacle_avoidance_response(enabled=True):
    resp = MagicMock()
    resp.success = True
    resp.message = ""
    resp.current_enabled = enabled
    return resp


def _make_robot_state_response(state_name="passive", speed_ratio=50, oa=True):
    resp = MagicMock()
    resp.success = True
    resp.message = ""
    resp.current_state = state_name
    resp.current_speed_ratio = speed_ratio
    resp.obstacle_avoidance_enabled = oa

    # RobotState sub-message
    rs = MagicMock()
    rs.jpos_leg = [0.0] * 10
    rs.jpos_leg_des = [0.0] * 10
    rs.jvel_leg = [0.0] * 10
    rs.jvel_leg_des = [0.0] * 10
    rs.jtau_leg = [0.0] * 10
    rs.jtau_leg_des = [0.0] * 10
    rs.pos_body = [0.0, 0.0, 0.3]
    rs.vel_body = [0.0, 0.0, 0.0]
    rs.acc_body = [0.0, 0.0, 0.0]
    rs.omega_body = [0.0, 0.0, 0.0]
    rs.ori_body = [0.0, 0.0, 0.0]
    rs.grf_left = [0.0, 0.0, 50.0]
    rs.grf_right = [0.0, 0.0, 50.0]
    rs.grf_vertical_filtered = [50.0, 50.0]
    rs.temp = [0.0, 0.0, 0.0, 0.0]
    resp.robot_state = rs
    return resp


def _make_progress_final(success=True, msg=""):
    p = MagicMock()
    p.is_final = True
    p.success = success
    p.message = msg
    p.current_index = 0
    p.total_motions = 1
    p.current_motion_id = "balance_stand"
    p.current_state = "balance_stand"
    p.execution_id = "exec-001"
    return p


# ---------------------------------------------------------------------------
# Core fixture: a RobotClient with a fully-mocked gRPC stub
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_stub():
    """Bare mock stub with default responses wired."""
    stub = MagicMock()
    stub.SetSpeedRatio.return_value = _make_speed_ratio_response(50)
    stub.SetObstacleAvoidance.return_value = _make_obstacle_avoidance_response(
        True)
    stub.GetRobotState.return_value = _make_robot_state_response()
    stub.GetAvailableMotions.return_value = MagicMock(motions=[],
                                                      descriptions={},
                                                      success=True,
                                                      message="")
    # ExecuteSequence returns an iterable of progress messages
    stub.ExecuteSequence.return_value = iter([_make_progress_final(True)])
    return stub


@pytest.fixture
def robot(mock_stub):
    """A RobotClient whose channel and stub are fully mocked."""
    with patch("dobot_quad.robot_client.grpc.insecure_channel") as mock_channel, \
         patch("dobot_quad.robot_client.pb_grpc.gRPCServiceStub") as mock_stub_cls, \
         patch("dobot_quad.robot_client.time.sleep") as mock_sleep:
        mock_stub_cls.return_value = mock_stub
        mock_channel.return_value = MagicMock()

        from dobot_quad import RobotClient
        client = RobotClient("localhost:50051")
        # Expose stub for assertion in tests
        client._mock_stub = mock_stub
        client._mock_sleep = mock_sleep
        yield client
