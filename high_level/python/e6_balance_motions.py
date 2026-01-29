#!/usr/bin/env python3
import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_balance_demo(server_address: str = "localhost:50051", bpm: float = 120.0):
    """
    Execute Balance motions demo in BALANCE_STAND state.
    This demo includes four balance motions with bidirectional movement:
    nod (pitch), shake head (yaw), sway (roll), and squat (height).
    
    Args:
        server_address: Server address
        bpm: Beats per minute for motion timing
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}\n")

    print("Example 6: Balance Motions Demo")

    # Create motion sequence
    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="demo_balance_motions",
        sequence_name="Balance Motions Demo",
        bpm=bpm,
        loop=False
    )

    # Enter BALANCE_STAND state
    motion = sequence.motions.add()
    motion.motion_id = "path_to_state"
    motion.parameters.add(key="target_state", string_value="BALANCE_STAND")

    # Nod forward and backward
    motion = sequence.motions.add()
    motion.motion_id = "balance_pitch"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=0.8)

    motion = sequence.motions.add()
    motion.motion_id = "balance_pitch"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=-0.8)

    # Shake head right and left
    motion = sequence.motions.add()
    motion.motion_id = "balance_yaw"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=0.8)

    motion = sequence.motions.add()
    motion.motion_id = "balance_yaw"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=-0.8)

    # Sway right and left
    motion = sequence.motions.add()
    motion.motion_id = "balance_roll"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=0.8)

    motion = sequence.motions.add()
    motion.motion_id = "balance_roll"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=-0.8)

    # Squat
    motion = sequence.motions.add()
    motion.motion_id = "balance_height"
    motion.parameters.add(key="beats", float_value=2.0)
    motion.parameters.add(key="amplitude", float_value=-0.8)

    # Return to neutral pose
    motion = sequence.motions.add()
    motion.motion_id = "balance_neutral"
    motion.parameters.add(key="beats", float_value=1.0)
    motion.parameters.add(key="amplitude", float_value=0.0)

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
        return
    except grpc.RpcError as e:
        print(f"Execution failed: {e.code().name} - {e.details()}")
        return

    if response.success:
        print(f"Balance motions demo executed successfully")
        print(f"  Execution ID: {response.execution_id}")
    else:
        print(f"Execution failed: {response.message}")

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    bpm = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0

    run_balance_demo(server, bpm)
