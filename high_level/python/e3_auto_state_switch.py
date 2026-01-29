#!/usr/bin/env python3

import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_demo(target_state: str = "BALANCE_STAND", server_address: str = "localhost:50051"):
    """
    Execute automatic state switching demo. Different from e1, user doesn't need to know the state transition path. As long as the target state is given, the system will figure out the transition path automatically, which is suitable for fast switching between various states.
    
    This motion's id is "path_to_state" and its parameter's key is "target_state". These have to be specified. 
    Args:
        target_state: target state name
        server_address: server address
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Example 3: PATH_TO_STATE Automatic State Switching Demo")
    print(f"Target state: {target_state}")

    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="path_to_state", sequence_name="Automatically State Machine Switching Demo", loop=False
    )

    # path_to_state motion
    motion = sequence.motions.add()
    motion.motion_id = "path_to_state"
    motion.parameters.add(key="target_state", string_value=target_state)

    # Execute sequence
    request = grpc_service_pb2.ExecuteSequenceRequest(sequence=sequence, immediate_start=True)

    call = stub.ExecuteSequence.future(request)
    print("\nSequence is running... Press Ctrl+C to cancel.")

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
        print(f"\nFailed to switch state: {e.code().name} - {e.details()}")
        return

    if response.success:
        print(f"\nSuccessfully switched to state: {target_state}")
        print(f"  Execution ID: {response.execution_id}")
        print(f"  Message: {response.message}")
    else:
        print(f"\nFailed to switch state: {response.message}")

    channel.close()


def interactive_demo(server_address: str = "localhost:50051"):
    """Interactive target state selection"""
    state_list = [
        "PASSIVE",
        "STAND_DOWN",
        "STAND_UP",
        "BALANCE_STAND",
        "WALK",
        "RL",
        "FLYING_TROT",
        "WAVE",
        "DANCE0",
        "BACK_FLIP",
        "JUMP",
    ]

    print("\nAvailable target states:")
    for idx, state in enumerate(state_list):
        print(f"  {idx}. {state}")

    try:
        choice = int(input("\nPlease select the index of the target state: ").strip())
        if 0 <= choice < len(state_list):
            target_state = state_list[choice]
        else:
            print("Invalid index, using default state BALANCE_STAND")
            target_state = "BALANCE_STAND"
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\nUsing default state BALANCE_STAND")
        target_state = "BALANCE_STAND"

    run_demo(target_state, server_address)


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"

    if len(sys.argv) > 2:
        target = sys.argv[2]
        run_demo(target, server)
    else:
        interactive_demo(server)
