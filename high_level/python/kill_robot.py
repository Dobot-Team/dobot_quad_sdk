#!/usr/bin/env python3

import grpc
import sys
import time

try:
    from proto import grpc_service_pb2
    from proto import grpc_service_pb2_grpc
except ImportError:
    # If running from the same directory as the generated files
    import grpc_service_pb2
    import grpc_service_pb2_grpc


def run_kill_robot(server_address: str = "localhost:50051"):
    """
    Execute 'kill_robot' motion to shut down the controller.
    """
    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Executing KILL_ROBOT command...")
    print("WARNING: This will switch robot to PASSIVE, wait 5s, and KILL all controller processes!")

    # Confirm action
    confirm = input("Are you sure? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        return

    sequence = grpc_service_pb2.MotionSequence(
        sequence_id="shutdown_seq", sequence_name="Kill Robot Sequence", loop=False
    )

    # kill_robot motion
    motion = sequence.motions.add()
    motion.motion_id = "kill_robot"
    # No parameters needed

    # Execute sequence
    request = grpc_service_pb2.ExecuteSequenceRequest(sequence=sequence, immediate_start=True)

    call = stub.ExecuteSequence.future(request)

    try:
        response = call.result(timeout=10)
        print("Kill robot command executed successfully.")
    except grpc.RpcError as e:
        # If the server closes the connection after receiving kill_robot,
        # it means the command was executed successfully
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print("Kill robot command executed successfully (server shut down as expected).")
        else:
            print(f"Error executing kill_robot: {e}")
            raise
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected, cancelling execution...")
        call.cancel()
        return

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    run_kill_robot(server_address=server)
