#!/usr/bin/env python3
import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_walk_demo(server_address: str = "localhost:50051"):
    """
    Execute Walk velocity sequence demo. This function is achieved by setting parameter under WALK or FLYING_TROT state. So make sure the robot is in WALK state before delivering velocity sequence.

    The format of velocity sequence is: "vx,vy,vyaw,duration;...". Each segment defines the linear velocities in x (vx), y (vy), angular velocity around z (vyaw), and duration to maintain these velocities. The units are in meters per second for vx and vy, radians per second for vyaw, and seconds for duration.  
    
    Args:
        server_address: Server address
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Example 4a: Walk 3D Velocity Sequence Demo")
    print("Move forward, backward, left, right + rotate")

    # Create motion sequence
    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="demo_walk_velocity", sequence_name="Walk Velocity Sequence Demo", loop=False
    )

    # Enter WALK state
    motion1 = sequence.motions.add()
    motion1.motion_id = "path_to_state"
    motion1.parameters.add(key="target_state", string_value="WALK")

    # Walk velocity sequence
    # Format: "vx,vy,vyaw,duration;..."
    velocity_sequence = (
        # "0.0,0.5,0.0,2.0;"  # forward
        # "0.0,0.5,0.3,2.0;"  # forward + turn right
        # "0.4,0.0,0.0,1.5;"  # right strafe
        # "0.0,-0.3,-0.3,2.0;"  # backward + turn left
        # "0.0,0.0,-0.5,1.5;"  # in-place turn left
        # "0.0,0.0,0.0,1.0"  # stop
        "0.0,0.0,0.6,2.5;"  # in-place turn right
        "0.0,0.0,-0.6,2.5;"  # in-place turn left
        "0.0,0.0,0.0,1.0"  # stop
    )

    motion2 = sequence.motions.add()
    motion2.motion_id = "walk"
    motion2.parameters.add(key="velocity_sequence", string_value=velocity_sequence)

    # add motion to stand_down
    motion3 = sequence.motions.add()
    motion3.motion_id = "path_to_state"
    motion3.parameters.add(key="target_state", string_value="STAND_DOWN")

    # Execute sequence
    request = grpc_service_pb2.ExecuteSequenceRequest(sequence=sequence, immediate_start=True)
    call = stub.ExecuteSequence.future(request)
    print("\nSequence is running... Press Ctrl+C to stop.")

    try:
        while True:
            try:
                response = call.result(timeout=0.5)
                break
            except grpc.FutureTimeoutError:
                continue
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected, cancelling execution...")
        call.cancel()
        try:
            call.result()
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Sequence cancelled by user.")
            else:
                print(f"Sequence aborted: {e.code().name} - {e.details()}")
        channel.close()
        return
    except grpc.RpcError as e:
        print(f"\nExecution failed: {e.code().name} - {e.details()}")
        channel.close()
        return

    if response.success:
        print(f"\nWalk velocity sequence demo executed successfully")
        print(f"  Execution ID: {response.execution_id}")
        print(f"  Total duration: ~11 seconds")
    else:
        print(f"\nExecution failed: {response.message}")

    channel.close()


def run_flying_trot_demo(server_address: str = "localhost:50051"):
    """
    Execute Flying Trot velocity sequence demo. This is the same as the Walk velocity sequence demo but in FLYING_TROT state.
    
    Args:
        server_address: Server address
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Example 4b: Flying Trot 3D Velocity Sequence Demo")
    print("High-speed sprint + sharp turns + rapid rotation")

    # Create motion sequence
    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="demo_flying_trot_velocity",
        sequence_name="Flying Trot 3D Velocity Sequence Demo",
        bpm=120.0,
        loop=False,
    )

    # Enter FLYING_TROT state
    motion1 = sequence.motions.add()
    motion1.motion_id = "path_to_state"
    motion1.parameters.add(key="target_state", string_value="FLYING_TROT")

    # Flying Trot velocity sequence
    velocity_sequence = (
        # "0.0,0.8,0.0,3.0;"  # High-speed sprint
        # "0.0,0.7,0.5,2.0;"  # Forward + sharp turn
        # "0.6,0.0,0.0,2.0;"  # High-speed right strafe
        # "0.0,0.4,-0.4,2.0;"  # Decelerate + turn
        # "0.0,0.0,0.6,1.5;"  # In-place rapid rotation
        # "0.0,0.0,0.0,1.0"  # Stop
        "0.0,0.0,0.2,1.5;"  # in-place turn right
        "0.0,0.0,-0.2,1.5;"  # in-place turn left
        "0.0,0.0,0.0,1.0"  # stop
    )
    motion2 = sequence.motions.add()
    motion2.motion_id = "flying_trot"
    motion2.parameters.add(key="velocity_sequence", string_value=velocity_sequence)

    # add motion to stand_down
    motion3 = sequence.motions.add()
    motion3.motion_id = "path_to_state"
    motion3.parameters.add(key="target_state", string_value="STAND_DOWN")

    # Execute sequence
    request = grpc_service_pb2.ExecuteSequenceRequest(sequence=sequence, immediate_start=True)
    call = stub.ExecuteSequence.future(request)
    print("\nSequence is running... Press Ctrl+C to stop.")

    try:
        while True:
            try:
                response = call.result(timeout=0.5)
                break
            except grpc.FutureTimeoutError:
                continue
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected, cancelling execution...")
        call.cancel()
        try:
            call.result()
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Sequence cancelled by user.")
            else:
                print(f"Sequence aborted: {e.code().name} - {e.details()}")
        channel.close()
        return
    except grpc.RpcError as e:
        print(f"\nExecution failed: {e.code().name} - {e.details()}")
        channel.close()
        return

    if response.success:
        print(f"\nFlying Trot velocity sequence demo executed successfully")
        print(f"  Execution ID: {response.execution_id}")
        print(f"  Total duration: ~12.5 seconds")
    else:
        print(f"\n✗ Execution failed: {response.message}")


def run_rl_demo(server_address: str = "localhost:50051"):
    """
    Execute RL velocity sequence demo. This is the same as the Walk velocity sequence demo but in RL state.
    
    Args:
        server_address: Server address
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Example 4c: RL 3D Velocity Sequence Demo")
    print("Move forward, backward, left, right + rotate")

    # Create motion sequence
    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="demo_rl_velocity", sequence_name="RL Velocity Sequence Demo", loop=False
    )

    # Enter RL state
    motion1 = sequence.motions.add()
    motion1.motion_id = "path_to_state"
    motion1.parameters.add(key="target_state", string_value="RL")

    # RL velocity sequence
    # Format: "vx,vy,vyaw,duration;..."
    velocity_sequence = (
        # "0.0,0.5,0.0,2.0;"  # forward
        # "0.0,0.5,0.3,2.0;"  # forward + turn right
        # "0.4,0.0,0.0,1.5;"  # right strafe
        # "0.0,-0.3,-0.3,2.0;"  # backward + turn left
        "0.0,0.0,0.2,2.0;"  # in-place turn right
        "0.0,0.0,-0.2,2.0;"  # in-place turn left
        "0.0,0.0,0.0,1.0"  # stop
    )

    motion2 = sequence.motions.add()
    motion2.motion_id = "rl"
    motion2.parameters.add(key="velocity_sequence", string_value=velocity_sequence)

    # add motion to stand_down
    motion3 = sequence.motions.add()
    motion3.motion_id = "path_to_state"
    motion3.parameters.add(key="target_state", string_value="STAND_DOWN")

    # Execute sequence
    request = grpc_service_pb2.ExecuteSequenceRequest(sequence=sequence, immediate_start=True)
    call = stub.ExecuteSequence.future(request)
    print("\nSequence is running... Press Ctrl+C to stop.")

    try:
        while True:
            try:
                response = call.result(timeout=0.5)
                break
            except grpc.FutureTimeoutError:
                continue
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected, cancelling execution...")
        call.cancel()
        try:
            call.result()
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.CANCELLED:
                print("Sequence cancelled by user.")
            else:
                print(f"Sequence aborted: {e.code().name} - {e.details()}")
        channel.close()
        return
    except grpc.RpcError as e:
        print(f"\nExecution failed: {e.code().name} - {e.details()}")
        channel.close()
        return

    if response.success:
        print(f"\nRL velocity sequence demo executed successfully")
        print(f"  Execution ID: {response.execution_id}")
        print(f"  Total duration: ~11 seconds")
    else:
        print(f"\nExecution failed: {response.message}")

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"

    print("\n=== Velocity Sequence Demo Selection ===")
    print("1. Walk Demo")
    print("2. Flying Trot Demo")
    print("3. RL Demo")
    print("=====================================")

    choice = input("Please select a demo (1/2/3) [default: 1]: ").strip()

    if choice == "2":
        run_flying_trot_demo(server)
    elif choice == "3":
        run_rl_demo(server)
    else:
        run_walk_demo(server)
