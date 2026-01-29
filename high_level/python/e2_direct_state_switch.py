#!/usr/bin/env python3
import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_e2(server_address: str = "localhost:50051"):
    """
    states are switched by hands. User has to know which states are available under the current condition. Here we demonstrate a simple state switching sequence which is STAND_DOWN -> STAND_UP -> BALANCE_STAND -> DANCE0.
    
    This motion's id are "passive", "stand_down", "stand_up", "balance_stand", "dance0", etc. These have to be specified.
    Args:
        server_address: server address
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"✓ Connected to server: {server_address}")

    print("example 2: Direct State Switching Demo")
    print("STAND_DOWN -> STAND_UP -> BALANCE_STAND -> DANCE0")

    # Create motion sequence
    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="demo_state_switch", sequence_name="Directly State Machine Switching Demo", loop=False
    )

    # Add motions to sequence in order
    # motion_ids = ["passive", "stand_down", "stand_up", "balance_stand", "dance0"]
    motion_ids = ["passive", "stand_down", "stand_up", "x_legs", "balance_stand"]
    for motion_id in motion_ids:
        motion = sequence.motions.add()
        motion.motion_id = motion_id

    # request define
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
        print(f"\nExecution failed: {e.code().name} - {e.details()}")
        return

    if response.success:
        print(f"\nState switching demo executed successfully")
        print(f"  Execution ID: {response.execution_id}")
        print(f"  Message: {response.message}")
        print(f"  Number of motions: {len(sequence.motions)}")
        print(f"  BPM: {sequence.bpm}")
    else:
        print(f"\nExecution failed: {response.message}")

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    run_e2(server)
