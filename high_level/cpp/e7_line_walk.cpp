// Example 7: Walk in a straight line or at an angle.
// Usage: ./e7_line_walk [server_address] [direction] [distance]
//   direction: 0=front (default), 1=back, 2=left, 3=right
//   distance:  meters (default 3.0)
//
// Simplified API:
//   client.line_walk(0, 3.0);        // front 3m
//   client.walk_forward(3.0);        // same thing
//   client.move_left(2.0);           // strafe left 2m
//   client.rotate_walk(-45, 2.0);    // walk at -45° (left turn)
//   client.rotate_walk(90, 1.0);     // walk at 90° (right turn)

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);
    int dir = (argc > 2) ? std::stoi(argv[2]) : 0;
    float dist = (argc > 3) ? std::stof(argv[3]) : 3.0f;

    const char* names[] = {"front", "back", "left", "right"};
    std::cout << "Line Walk: " << names[dir] << " " << dist << "m" << std::endl;

    bool ok = client.line_walk(dir, dist);

    // Demonstrate rotate_walk with signed angles
    if (ok) {
        std::cout << "\nRotate Walk Demo:" << std::endl;
        std::cout << "  -45° (left turn): ";
        client.rotate_walk(-45, 1.0, 80, true);

        std::cout << "  90° (right turn): ";
        client.rotate_walk(90, 1.0, 80, true);
    }

    return ok ? 0 : 1;
}
