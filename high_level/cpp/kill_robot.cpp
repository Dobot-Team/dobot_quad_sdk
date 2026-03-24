// Kill Robot: Emergency shutdown (PASSIVE -> kill controller processes).
// Usage: ./kill_robot [server_address]

#include "robot_client.h"

int main(int argc, char** argv)
{
    std::string confirm;
    std::cout << "Kill robot controller? (y/N): ";
    std::cin >> confirm;
    if (confirm != "y" && confirm != "Y") {
        std::cout << "Aborted." << std::endl;
        return 0;
    }

    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    auto req = robot::make_request("kill");
    req.mutable_sequence()->add_motions()->set_motion_id("kill_robot");
    client.execute(req);
    return 0;
}
