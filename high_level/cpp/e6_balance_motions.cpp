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

class BalanceMotionsClient
{
public:
    explicit BalanceMotionsClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    // Execute balance motions demo with optional BPM parameter.
    bool Run(double bpm = 120.0)
    {
        std::cout << "Connected to server: " << server_address_ << "\n" << std::endl;
        std::cout << "Example 6: Balance Motions Demo" << std::endl;

        ExecuteSequenceRequest request;
        auto* sequence = request.mutable_sequence();
        sequence->set_sequence_id("demo_balance_motions");
        sequence->set_sequence_name("Balance Motions Demo");
        sequence->set_bpm(bpm);
        sequence->set_loop(false);

        auto add_motion = [sequence](const std::string& id, float beats, float amp) {
            auto* m = sequence->add_motions();
            m->set_motion_id(id);
            m->mutable_parameters()->Add()->set_key("beats");
            m->mutable_parameters(0)->set_float_value(beats);
            m->mutable_parameters()->Add()->set_key("amplitude");
            m->mutable_parameters(1)->set_float_value(amp);
        };

        auto* motion = sequence->add_motions();
        motion->set_motion_id("path_to_state");
        motion->mutable_parameters()->Add()->set_key("target_state");
        motion->mutable_parameters(0)->set_string_value("BALANCE_STAND");

        add_motion("balance_pitch", 1.0f, 0.8f);
        add_motion("balance_pitch", 1.0f, -0.8f);
        add_motion("balance_yaw", 1.0f, 0.8f);
        add_motion("balance_yaw", 1.0f, -0.8f);
        add_motion("balance_roll", 1.0f, 0.8f);
        add_motion("balance_roll", 1.0f, -0.8f);
        add_motion("balance_height", 2.0f, -0.8f);
        add_motion("balance_neutral", 1.0f, 0.0f);

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
                std::cout << "Balance motions demo executed successfully" << std::endl;
                std::cout << "  Execution ID: " << response.execution_id() << std::endl;
            } else {
                std::cout << "Execution failed: " << response.message() << std::endl;
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
    double bpm = (argc > 2) ? std::stod(argv[2]) : 120.0;

    BalanceMotionsClient client(server_address);
    return client.Run(bpm) ? 0 : 1;
}
