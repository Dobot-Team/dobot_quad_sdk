// Example 1: List all available motions and their parameters.
// Usage: ./e1_get_available_motions [server_address]

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    auto res = client.get_motions();

    if (!res.success()) {
        std::cerr << "Failed: " << res.message() << std::endl;
        return 1;
    }

    std::cout << "Available motions (" << res.motions_size() << "):\n" << std::endl;

    for (const auto& m : res.motions()) {
        std::cout << "  [" << m.motion_id() << "]";
        auto it = res.descriptions().find(m.motion_id());
        if (it != res.descriptions().end())
            std::cout << " - " << it->second;
        std::cout << std::endl;

        for (const auto& p : m.parameters()) {
            std::cout << "      " << p.key() << ": ";
            switch (p.value_case()) {
                case grpc_comm::Parameter::kFloatValue:
                    std::cout << p.float_value();
                    break;
                case grpc_comm::Parameter::kIntValue:
                    std::cout << p.int_value();
                    break;
                case grpc_comm::Parameter::kStringValue:
                    std::cout << '"' << p.string_value() << '"';
                    break;
                case grpc_comm::Parameter::kBoolValue:
                    std::cout << (p.bool_value() ? "true" : "false");
                    break;
                default:
                    std::cout << "(unset)";
            }
            std::cout << std::endl;
        }
    }
    return 0;
}
