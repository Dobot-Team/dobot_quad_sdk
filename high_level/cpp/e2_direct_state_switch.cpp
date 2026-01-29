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

class DirectStateSwitchClient
{
public:
    explicit DirectStateSwitchClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    bool Run()
    {
        std::cout << "✓ Connected to server: " << server_address_ << std::endl;
        std::cout << "example 2: Direct State Switching Demo" << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("demo_state_switch");
        sequence->set_sequence_name("Directly State Machine Switching Demo");
        sequence->set_loop(false);

        for (const auto& id : {"passive", "stand_down", "stand_up", "x_legs", "balance_stand"}) {
            sequence->add_motions()->set_motion_id(id);
        }
        request.set_immediate_start(true);

        std::cout << "\nSequence is running... Press Ctrl+C to stop." << std::endl;

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
            std::cout << "\nState switching demo executed successfully" << std::endl;
            std::cout << "  Execution ID: " << response.execution_id() << std::endl;
            std::cout << "  Message: " << response.message() << std::endl;
            std::cout << "  Number of motions: " << sequence->motions_size() << std::endl;
        } else {
            std::cout << "\nExecution failed: " << response.message() << std::endl;
        }
        return response.success();
    }

private:
    std::unique_ptr<gRPCService::Stub> stub_;
    std::string server_address_;
};

int main(int argc, char** argv)
{
    const std::string server_address = (argc > 1) ? argv[1] : "192.168.5.2:50051";

    // Register Ctrl+C handler
    std::signal(SIGINT, SignalHandler);

    DirectStateSwitchClient client(server_address);
    return client.Run() ? 0 : 1;
}
