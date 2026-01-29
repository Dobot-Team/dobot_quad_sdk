#include <iostream>
#include <iomanip>
#include <memory>
#include <string>
#include <grpcpp/grpcpp.h>
#include "proto/grpc_service.grpc.pb.h"

using grpc_comm::GetRobotStateRequest;
using grpc_comm::GetRobotStateResponse;
using grpc_comm::gRPCService;

class RobotStateClient
{
public:
    explicit RobotStateClient(const std::string& server_address)
        : server_address_(server_address)
    {
        auto channel = grpc::CreateChannel(server_address_, grpc::InsecureChannelCredentials());
        stub_ = gRPCService::NewStub(channel);
    }

    bool PrintState()
    {
        std::cout << "Connected to server: " << server_address_ << std::endl;
        std::cout << "\nFetching robot state..." << std::endl;

        GetRobotStateRequest request;
        GetRobotStateResponse response;
        grpc::ClientContext context;

        auto status = stub_->GetRobotState(&context, request, &response);
        if (!status.ok()) {
            std::cout << "Failed to get robot state: " << status.error_message() << std::endl;
            return false;
        }

        if (!response.success()) {
            std::cout << "Failed to retrieve state: " << response.message() << std::endl;
            return false;
        }

        std::cout << "\nRobot state retrieved successfully" << std::endl;
        std::cout << "  Message: " << response.message() << "\n" << std::endl;
        std::cout << "Robot State Data:" << std::endl;

        const auto& state = response.robot_state();
        auto print_array = [](const google::protobuf::RepeatedField<float>& arr, const std::string& label) {
            std::cout << label << ": [";
            for (int i = 0; i < arr.size(); ++i) {
                if (i > 0)
                    std::cout << ", ";
                std::cout << std::fixed << std::setprecision(2) << arr[i];
            }
            std::cout << "]" << std::endl;
        };

        std::cout << "\nLeg Joints [rad] / [rad/s] / [Nm]:" << std::endl;
        print_array(state.jpos_leg(), "  Positions [rad]");
        print_array(state.jpos_leg_des(), "  Desired Positions [rad]");
        print_array(state.jvel_leg(), "  Velocities [rad/s]");
        print_array(state.jvel_leg_des(), "  Desired Velocities [rad/s]");
        print_array(state.jtau_leg(), "  Torques [Nm]");
        print_array(state.jtau_leg_des(), "  Desired Torques [Nm]");

        if (state.jpos_arm_size() > 0) {
            std::cout << "\nArm Joints [rad] / [rad/s] / [Nm]:" << std::endl;
            print_array(state.jpos_arm(), "  Positions [rad]");
            print_array(state.jvel_arm(), "  Velocities [rad/s]");
            print_array(state.jtau_arm(), "  Torques [Nm]");
        }

        std::cout << "\nBody State:" << std::endl;
        print_array(state.pos_body(), "  Position (x,y,z) [m]");
        print_array(state.vel_body(), "  Velocity [m/s]");
        print_array(state.acc_body(), "  Acceleration [m/s²]");
        print_array(state.omega_body(), "  Angular Velocity [rad/s]");
        print_array(state.ori_body(), "  Orientation (roll,pitch,yaw) [rad]");

        std::cout << "\nContact Forces [N]:" << std::endl;
        print_array(state.grf_left(), "  Left Foot [N]");
        print_array(state.grf_right(), "  Right Foot [N]");
        print_array(state.grf_vertical_filtered(), "  Vertical Filtered [N]");

        if (state.temp_size() >= 10) {
            std::cout << "\nAdditional Data:" << std::endl;
            std::cout << "  Total Contact Force X [N]: " << std::fixed << std::setprecision(2) << state.temp(0)
                      << std::endl;
            std::cout << "  Total Contact Force Y [N]: " << std::fixed << std::setprecision(2) << state.temp(1)
                      << std::endl;
            std::cout << "  Total Contact Force Z [N]: " << std::fixed << std::setprecision(2) << state.temp(2)
                      << std::endl;
            std::cout << "  Total GRF X [N]: " << std::fixed << std::setprecision(2) << state.temp(3) << std::endl;
            std::cout << "  Battery Voltage 1 [V]: " << std::fixed << std::setprecision(2) << state.temp(8)
                      << std::endl;
            std::cout << "  Battery Voltage 2 [V]: " << std::fixed << std::setprecision(2) << state.temp(9)
                      << std::endl;
        }

        std::cout << "\n" << std::string(60, '=') << std::endl;
        return true;
    }

private:
    std::unique_ptr<gRPCService::Stub> stub_;
    std::string server_address_;
};

int main(int argc, char** argv)
{
    const std::string server_address = (argc > 1) ? argv[1] : "192.168.5.2:50051";
    RobotStateClient client(server_address);
    return client.PrintState() ? 0 : 1;
}
