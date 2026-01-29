#include <iostream>
#include <string>
#include <grpcpp/grpcpp.h>
#include "proto/grpc_service.grpc.pb.h"

using grpc_comm::GetMotionsRequest;
using grpc_comm::GetMotionsResponse;
using grpc_comm::gRPCService;

class MotionClient
{
public:
    explicit MotionClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    // Query and print all available motions.
    bool Run()
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "Example 1: Get Available Motions" << std::endl;

        GetMotionsRequest request;
        GetMotionsResponse response;
        grpc::ClientContext context;

        auto status = stub_->GetAvailableMotions(&context, request, &response);
        if (!status.ok()) {
            std::cout << "RPC failed: " << status.error_message() << std::endl;
            return false;
        }
        if (!response.success()) {
            std::cout << "Failed to retrieve motions: " << response.message() << std::endl;
            return false;
        }

        std::cout << "Successfully retrieved motion list: " << response.message() << std::endl;
        std::cout << "Found " << response.motions_size() << " motions:\n" << std::endl;

        for (const auto& motion : response.motions()) {
            const std::string& motion_id = motion.motion_id();
            std::cout << "  [" << motion_id << "]" << std::endl;

            auto desc_it = response.descriptions().find(motion_id);
            if (desc_it != response.descriptions().end()) {
                std::cout << "    Description: " << desc_it->second << std::endl;
            }

            if (motion.parameters_size() > 0) {
                std::cout << "    Parameters (default values):" << std::endl;
                for (const auto& param : motion.parameters()) {
                    std::cout << "      - " << param.key() << ": ";
                    switch (param.value_case()) {
                        case grpc_comm::Parameter::kFloatValue:
                            std::cout << param.float_value() << " (float)";
                            break;
                        case grpc_comm::Parameter::kIntValue:
                            std::cout << param.int_value() << " (int)";
                            break;
                        case grpc_comm::Parameter::kStringValue:
                            std::cout << '"' << param.string_value() << '"' << " (string)";
                            break;
                        case grpc_comm::Parameter::kBoolValue:
                            std::cout << (param.bool_value() ? "true" : "false") << " (bool)";
                            break;
                        default:
                            std::cout << "(not set)";
                            break;
                    }
                    std::cout << std::endl;
                }
            }
            std::cout << std::endl;
        }
        return true;
    }

private:
    std::unique_ptr<gRPCService::Stub> stub_;
    std::string server_address_;
};

int main(int argc, char** argv)
{
    const std::string server_address = (argc > 1) ? argv[1] : "192.168.5.2:50051";
    MotionClient client(server_address);
    return client.Run() ? 0 : 1;
}
