// Example 8: Rotate in place.
// Usage: ./e8_rotation [server_address] [direction] [angle]
//   direction: 0=left/CCW (default), 1=right/CW
//   angle:     degrees (default 90)
//
// Simplified API:
//   client.rotate("left", 90);   // left 90 degrees
//   client.rotate_left(90);      // same thing
//   client.rotate_right(45);     // right 45 degrees

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);
    int dir = (argc > 2) ? std::stoi(argv[2]) : 0;
    float angle = (argc > 3) ? std::stof(argv[3]) : 90.0f;
    dir = (dir == 1) ? 1 : 0;

    std::cout << "Rotation: " << (dir == 0 ? "left (CCW)" : "right (CW)") << " " << angle << " deg" << std::endl;
    client.rotate(dir, angle);
    client.circle(dir == 0 ? "left" : "right", 3);

    return 0;
}
