#include <atomic>
#include <chrono>
#include <csignal>
#include <iostream>
#include <memory>
#include <string>
#include <thread>
#include <grpcpp/grpcpp.h>
#include "proto/grpc_service.grpc.pb.h"

using grpc_comm::ExecuteSequenceRequest;
using grpc_comm::ExecuteSequenceResponse;
using grpc_comm::gRPCService;
using grpc_comm::MotionSequence;

std::atomic<bool> g_interrupt {false};
void SignalHandler(int)
{
    g_interrupt.store(true);
}
class AutoStateSwitchClient
{
public:
    explicit AutoStateSwitchClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    bool Run(const std::string& target_state)
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "Example 3: PATH_TO_STATE Automatic State Switching Demo" << std::endl;
        std::cout << "Target state: " << target_state << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("path_to_state");
        sequence->set_sequence_name("Automatically State Machine Switching Demo");
        sequence->set_loop(false);

        auto* motion = sequence->add_motions();
        motion->set_motion_id("path_to_state");
        auto* param = motion->add_parameters();
        param->set_key("target_state");
        param->set_string_value(target_state);

        request.set_immediate_start(true);

        std::cout << "\nSequence is running... Press Ctrl+C to cancel." << std::endl;

        ExecuteSequenceResponse response;
        grpc::ClientContext context;
        grpc::Status status;
        bool finished = false;
        bool cancelled = false;

        std::thread rpc_thread([&] {
            status = stub_->ExecuteSequence(&context, request, &response);
            finished = true;
        });
        rpc_thread.detach();

        while (!finished) {
            if (g_interrupt.exchange(false)) {
                cancelled = true;
                context.TryCancel();
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        if (!status.ok()) {
            if (status.error_code() == grpc::StatusCode::CANCELLED && cancelled) {
                std::cout << "Sequence cancelled by user." << std::endl;
            } else {
                std::cout << "RPC failed: " << status.error_message() << std::endl;
            }
            return false;
        }

        if (response.success()) {
            std::cout << "\nSuccessfully switched to state: " << target_state << std::endl;
            std::cout << "  Execution ID: " << response.execution_id() << std::endl;
            std::cout << "  Message: " << response.message() << std::endl;
        } else {
            std::cout << "\nFailed to switch state: " << response.message() << std::endl;
        }
        return response.success();
    }

    void Interactive()
    {
        const std::vector<std::string> states = {"PASSIVE", "STAND_DOWN", "STAND_UP", "BALANCE_STAND", "WALK", "RL",
            "FLYING_TROT", "WAVE", "DANCE0", "BACK_FLIP", "JUMP"};

        std::cout << "\nAvailable target states:" << std::endl;
        for (size_t i = 0; i < states.size(); ++i) {
            std::cout << "  " << i << ". " << states[i] << std::endl;
        }

        std::cout << "\nPlease select the index of the target state: ";
        int choice = -1;
        std::string target_state = "BALANCE_STAND";

        if (std::cin >> choice && choice >= 0 && choice < static_cast<int>(states.size())) {
            target_state = states[choice];
        } else {
            std::cout << "Invalid index, using default state BALANCE_STAND" << std::endl;
        }

        Run(target_state);
    }

private:
    std::unique_ptr<gRPCService::Stub> stub_;
    std::string server_address_;
};

int main(int argc, char** argv)
{
    // Register Ctrl+C handler
    std::signal(SIGINT, SignalHandler);

    const std::string server_address = (argc > 1) ? argv[1] : "192.168.5.2:50051";
    AutoStateSwitchClient client(server_address);

    if (argc > 2) {
        return client.Run(argv[2]) ? 0 : 1;
    }
    client.Interactive();
    return 0;
}
