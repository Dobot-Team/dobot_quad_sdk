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

class VelocitySequenceClient
{
public:
    explicit VelocitySequenceClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    // Execute the walk demo sequence.
    bool RunWalkDemo()
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "Example 4a: Walk 3D Velocity Sequence Demo" << std::endl;
        std::cout << "Move forward, backward, left, right + rotate\n" << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("demo_walk_velocity");
        sequence->set_sequence_name("Walk Velocity Sequence Demo");
        sequence->set_loop(false);

        auto* motion1 = sequence->add_motions();
        motion1->set_motion_id("path_to_state");
        motion1->mutable_parameters()->Add()->set_key("target_state");
        motion1->mutable_parameters(0)->set_string_value("WALK");

        auto* motion2 = sequence->add_motions();
        motion2->set_motion_id("walk");
        motion2->mutable_parameters()->Add()->set_key("velocity_sequence");
        motion2->mutable_parameters(0)->set_string_value(
            "0.0,0.0,0.6,3.0;0.0,0.0,-0.6,3.0;0.0,0.0,0.0,1.0;0.6,0.0,0.0,3.0;-0.6,0.0,0.0,3.0;0.0,0.0,0.0,1.0;");

        auto* motion3 = sequence->add_motions();
        motion3->set_motion_id("path_to_state");
        motion3->mutable_parameters()->Add()->set_key("target_state");
        motion3->mutable_parameters(0)->set_string_value("STAND_DOWN");

        request.set_immediate_start(true);

        std::cout << "Sequence is running... Press Ctrl+C to stop." << std::endl;
        ExecuteSequenceResponse response;
        grpc::ClientContext context;
        grpc::Status status;
        bool finished = false, cancelled = false;

        std::thread([&] {
            status = stub_->ExecuteSequence(&context, request, &response);
            finished = true;
        }).detach();

        while (!finished) {
            if (g_interrupt.exchange(false)) {
                cancelled = true;
                context.TryCancel();
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        if (status.ok() || (status.error_code() == grpc::StatusCode::CANCELLED && cancelled)) {
            if (response.success()) {
                std::cout << "\nVelocity sequence demo executed successfully" << std::endl;
                std::cout << "  Execution ID: " << response.execution_id() << std::endl;
            } else {
                std::cout << "\nExecution failed: " << response.message() << std::endl;
            }
            return response.success();
        }
        std::cout << "RPC failed: " << status.error_message() << std::endl;
        return false;
    }

    // Execute the flying trot demo sequence.
    bool RunFlyingTrotDemo()
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "Example 4b: Flying Trot 3D Velocity Sequence Demo" << std::endl;
        std::cout << "High-speed sprint + sharp turns + rapid rotation\n" << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("demo_flying_trot_velocity");
        sequence->set_sequence_name("Flying Trot 3D Velocity Sequence Demo");
        sequence->set_bpm(120.0);
        sequence->set_loop(false);

        auto* motion1 = sequence->add_motions();
        motion1->set_motion_id("path_to_state");
        motion1->mutable_parameters()->Add()->set_key("target_state");
        motion1->mutable_parameters(0)->set_string_value("FLYING_TROT");

        auto* motion2 = sequence->add_motions();
        motion2->set_motion_id("flying_trot");
        motion2->mutable_parameters()->Add()->set_key("velocity_sequence");
        motion2->mutable_parameters(0)->set_string_value("0.0,0.0,0.2,1.5;0.0,0.0,-0.2,1.5;0.0,0.0,0.0,1.0");

        auto* motion3 = sequence->add_motions();
        motion3->set_motion_id("path_to_state");
        motion3->mutable_parameters()->Add()->set_key("target_state");
        motion3->mutable_parameters(0)->set_string_value("STAND_DOWN");

        request.set_immediate_start(true);

        std::cout << "Sequence is running... Press Ctrl+C to stop." << std::endl;
        ExecuteSequenceResponse response;
        grpc::ClientContext context;
        grpc::Status status;
        bool finished = false, cancelled = false;

        std::thread([&] {
            status = stub_->ExecuteSequence(&context, request, &response);
            finished = true;
        }).detach();

        while (!finished) {
            if (g_interrupt.exchange(false)) {
                cancelled = true;
                std::cout << "\nKeyboardInterrupt detected, cancelling execution..." << std::endl;
                context.TryCancel();
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }

        if (status.ok() || (status.error_code() == grpc::StatusCode::CANCELLED && cancelled)) {
            if (response.success()) {
                std::cout << "\nVelocity sequence demo executed successfully" << std::endl;
                std::cout << "  Execution ID: " << response.execution_id() << std::endl;
            } else {
                std::cout << "\nExecution failed: " << response.message() << std::endl;
            }
            return response.success();
        }
        std::cout << "RPC failed: " << status.error_message() << std::endl;
        return false;
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
    VelocitySequenceClient client(server_address);

    std::string choice = "1";
    if (argc > 2) {
        choice = argv[2];
    }

    if (choice == "2") {
        return client.RunFlyingTrotDemo() ? 0 : 1;
    } else {
        return client.RunWalkDemo() ? 0 : 1;
    }
}
