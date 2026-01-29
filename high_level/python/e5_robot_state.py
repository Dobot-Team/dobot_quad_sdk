#!/usr/bin/env python3
import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_e5(server_address: str = "localhost:50051"):
    """
    Get current robot state including joint positions, velocities, torques, body pose, and contact forces.
    
    Args:
        server_address: server address
    """
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("\nFetching robot state...")

    request = grpc_service_pb2.GetRobotStateRequest()

    response = stub.GetRobotState(request)

    if response.success:
        state = response.robot_state

        print(f"\nRobot state retrieved successfully")
        print(f"  Message: {response.message}\n")
        print("Robot State Data:")

        print(f"\nLeg Joints [rad] / [rad/s] / [Nm]:")
        print(f"  Positions [rad]: {[f'{x:.2f}' for x in state.jpos_leg]}")
        print(f"  Desired Positions [rad]: {[f'{x:.2f}' for x in state.jpos_leg_des]}")
        print(f"  Velocities [rad/s]: {[f'{x:.2f}' for x in state.jvel_leg]}")
        print(f"  Desired Velocities [rad/s]: {[f'{x:.2f}' for x in state.jvel_leg_des]}")
        print(f"  Torques [Nm]: {[f'{x:.2f}' for x in state.jtau_leg]}")
        print(f"  Desired Torques [Nm]: {[f'{x:.2f}' for x in state.jtau_leg_des]}")

        if state.jpos_arm:
            print(f"\nArm Joints [rad] / [rad/s] / [Nm]:")
            print(f"  Positions [rad]: {[f'{x:.2f}' for x in state.jpos_arm]}")
            print(f"  Velocities [rad/s]: {[f'{x:.2f}' for x in state.jvel_arm]}")
            print(f"  Torques [Nm]: {[f'{x:.2f}' for x in state.jtau_arm]}")

        print(f"\nBody State:")
        print(f"  Position (x,y,z) [m]: {[f'{x:.2f}' for x in state.pos_body]}")
        print(f"  Velocity [m/s]: {[f'{x:.2f}' for x in state.vel_body]}")
        print(f"  Acceleration [m/s²]: {[f'{x:.2f}' for x in state.acc_body]}")
        print(f"  Angular Velocity [rad/s]: {[f'{x:.2f}' for x in state.omega_body]}")
        print(f"  Orientation (roll,pitch,yaw) [rad]: {[f'{x:.2f}' for x in state.ori_body]}")

        print(f"\nContact Forces [N]:")
        print(f"  Left Foot [N]: {[f'{x:.2f}' for x in state.grf_left]}")
        print(f"  Right Foot [N]: {[f'{x:.2f}' for x in state.grf_right]}")
        print(f"  Vertical Filtered [N]: {[f'{x:.2f}' for x in state.grf_vertical_filtered]}")

        if state.temp:
            print(f"\nAdditional Data:")
            temp_list = list(state.temp)
            if len(temp_list) >= 10:
                print(f"  Total Contact Force X [N]: {temp_list[0]:.2f}")
                print(f"  Total Contact Force Y [N]: {temp_list[1]:.2f}")
                print(f"  Total Contact Force Z [N]: {temp_list[2]:.2f}")
                print(f"  Total GRF X [N]: {temp_list[3]:.2f}")
                print(f"  Battery Voltage 1 [V]: {temp_list[8]:.2f}")
                print(f"  Battery Voltage 2 [V]: {temp_list[9]:.2f}")

        print(f"\n{'='*60}")
    else:
        print(f"\n✗ Failed to get robot state: {response.message}")

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    run_e5(server)
