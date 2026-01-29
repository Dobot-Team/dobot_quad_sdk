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

class KillRobotClient
{
public:
    explicit KillRobotClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    bool Run()
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "Executing KILL_ROBOT command..." << std::endl;
        std::cout << "WARNING: This will switch robot to PASSIVE, wait 5s, and KILL all controller processes!"
                  << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("shutdown_seq");
        sequence->set_sequence_name("Kill Robot Sequence");
        sequence->set_loop(false);

        auto* motion = sequence->add_motions();
        motion->set_motion_id("kill_robot");
        // No parameters needed for kill_robot

        request.set_immediate_start(true);

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
        return response.success();
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

    std::string confirmation;
    std::cout << "Are you sure you want to kill the robot controller? (y/n): ";
    std::cin >> confirmation;

    if (confirmation != "y" && confirmation != "Y") {
        std::cout << "Aborted." << std::endl;
        return 0;
    }

    KillRobotClient client(server_address);
    return client.Run() ? 0 : 1;
}
