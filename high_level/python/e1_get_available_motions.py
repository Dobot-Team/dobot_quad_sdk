#!/usr/bin/env python3
import grpc
import sys

from proto import grpc_service_pb2
from proto import grpc_service_pb2_grpc


def run_e1(server_address: str = "localhost:50051"):
    """
    Get all available motions from the server. This is useful to understand what motions are available 
    and what parameters they require before executing them.
    
    Args:
        server_address: server address
        fsm_state: optional FSM state filter, empty string returns all motions
    """

    # Establish connection
    channel = grpc.insecure_channel(server_address)
    stub = grpc_service_pb2_grpc.gRPCServiceStub(channel)
    print(f"Connected to server: {server_address}")

    print("Example 1: Get Available Motions")

    # Create request
    request = grpc_service_pb2.GetMotionsRequest()

    response = stub.GetAvailableMotions(request)

    if response.success:
        print(f"Successfully retrieved motion list: {response.message}")
        print(f"Found {len(response.motions)} motions:\n")

        for motion in response.motions:
            motion_id = motion.motion_id
            print(f"  [{motion_id}]")

            # description
            if motion_id in response.descriptions:
                print(f"    Description: {response.descriptions[motion_id]}")

            # some motion parameters
            if motion.parameters:
                print("    Parameters (default values):")
                for param in motion.parameters:
                    print(f"      - {param.key}: ", end="")

                    if param.HasField("float_value"):
                        print(f"{param.float_value} (float)")
                    elif param.HasField("int_value"):
                        print(f"{param.int_value} (int)")
                    elif param.HasField("string_value"):
                        print(f'"{param.string_value}" (string)')
                    elif param.HasField("bool_value"):
                        print(f"{'true' if param.bool_value else 'false'} (bool)")
                    else:
                        print("(not set)")
            print()

    else:
        print(f"\nFailed to retrieve motions: {response.message}")

    channel.close()


if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051"
    run_e1(server)
