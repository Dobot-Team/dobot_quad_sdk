// Example 6: Balance motions demo (pitch, yaw, roll, height).
// Usage: ./e6_balance_motions [server_address]
//
// Uses balance_sequence() to batch all motions into a SINGLE gRPC call.
//   client.balance_sequence({
//       {"balance_pitch",  15.0f, 2.0f, "dynamic"},
//       {"balance_neutral", 0.0f, 0.5f, "dynamic"},
//   });
//
// Individual calls are still available for one-off use:
//   client.balance_pitch(15.0f, 2.0f, "dynamic");  // nod ±15 degrees
//   client.balance_neutral();                        // return to neutral
//
// Two modes:
//   "dynamic" — sinusoidal sweep: 0 → value → 0 over duration.
//   "static"  — ramp to value, hold for duration, ramp back to 0.

#include "robot_client.h"

int main(int argc, char** argv)
{
    robot::Client client(argc > 1 ? argv[1] : "192.168.5.2:50051");
    robot::enable_safety_ready(client);

    if (client.is_quad_wheel()) {
        std::cerr << "Balance motions are not supported on MINI_QUAD_WHEEL." << std::endl;
        return 1;
    }

    client.balance_stand();

    std::cout << "\n=== Balance Motions Demo ===" << std::endl;
    std::cout << std::string(40, '-') << std::endl;

    // --- Part 1: Single-axis API (dynamic | min duration=0.5s) ---
    std::cout << "\n[Single-axis API | dynamic]" << std::endl;
    client.balance_pitch(15.0f, 0.5f, "dynamic");
    client.balance_yaw(20.0f, 0.5f, "dynamic");
    client.balance_roll(-30.0f, 0.5f, "dynamic");
    client.balance_height(-0.12f, 0.5f, "dynamic");
    client.balance_neutral();

    // --- Part 2: Single-axis API (static | max duration=5s) ---
    std::cout << "\n[Single-axis API | static]" << std::endl;
    client.balance_pitch(-15.0f, 5.0f, "static");
    client.balance_yaw(-20.0f, 5.0f, "static");
    client.balance_roll(30.0f, 5.0f, "static");
    client.balance_height(-0.12f, 5.0f, "static");
    client.balance_neutral();

    // --- Part 3: balance_sequence (dynamic) ---
    std::cout << "\n[balance_sequence | dynamic]" << std::endl;
    client.balance_sequence({
        {"balance_pitch", 15.0f, 0.5f, "dynamic"},   // nod forward 15°
        {"balance_pitch", -15.0f, 0.5f, "dynamic"},  // nod backward 15°
        {"balance_yaw", 20.0f, 0.5f, "dynamic"},     // look left 20°
        {"balance_yaw", -20.0f, 0.5f, "dynamic"},    // look right 20°
        {"balance_roll", 30.0f, 0.5f, "dynamic"},    // lean left 30°
        {"balance_roll", -30.0f, 0.5f, "dynamic"},   // lean right 30°
        {"balance_height", -0.12f, 0.5f, "dynamic"}, // squat 12cm
        {"balance_neutral", 0.0f, 0.5f, "dynamic"},  // return to neutral
    });

    // --- Part 4: balance_sequence (static) ---
    std::cout << "\n[balance_sequence | static]" << std::endl;
    client.balance_sequence({
        {"balance_pitch", 15.0f, 5.0f, "static"},   // hold pitch 15° for 5s
        {"balance_neutral", 0.0f, 0.5f, "dynamic"}, // neutral
        {"balance_yaw", 20.0f, 5.0f, "static"},     // hold yaw 20° for 5s
        {"balance_neutral", 0.0f, 0.5f, "dynamic"}, // neutral
        {"balance_height", -0.12f, 5.0f, "static"}, // hold squat 12cm for 5s
        {"balance_neutral", 0.0f, 0.5f, "dynamic"}, // neutral
    });

    // --- Part 5: Duration comparison ---
    std::cout << "\n[Duration comparison]" << std::endl;
    client.balance_sequence({
        {"balance_pitch", 15.0f, 0.5f, "dynamic"},  // fast sweep (0.5s)
        {"balance_pitch", 15.0f, 5.0f, "dynamic"},  // slow sweep (5s)
        {"balance_neutral", 0.0f, 0.5f, "dynamic"}, // neutral
    });

    // --- Part 6: Composite pose (all axes simultaneously, duration in [1,5]) ---
    std::cout << "\n[Dynamic pose - composite]" << std::endl;
    client.dynamic_pose(1.0f, 30.0f, 15.0f, 20.0f, -0.12f); // min duration, max offsets

    std::cout << "\n[Static pose - composite]" << std::endl;
    client.static_pose(5.0f, -30.0f, -15.0f, -20.0f, -0.12f); // max duration, opposite offsets

    client.balance_neutral();

    // --- Part 7: Composite pose progression (duration sweep and combinations) ---
    std::cout << "\n[Composite pose progression with different durations]" << std::endl;
    client.dynamic_pose(1.0f, 15.0f, 8.0f, 10.0f, -0.06f);
    client.dynamic_pose(2.5f, 22.0f, 12.0f, 15.0f, -0.09f);
    client.dynamic_pose(5.0f, 30.0f, 15.0f, 20.0f, -0.12f);
    client.balance_neutral();

    // --- Part 8: Static pose variations ---
    std::cout << "\n[Static pose variations]" << std::endl;
    client.static_pose(1.5f, -18.0f, -10.0f, -12.0f, -0.07f);
    client.static_pose(3.0f, -25.0f, -13.0f, -18.0f, -0.10f);
    client.static_pose(5.0f, -30.0f, -15.0f, -20.0f, -0.12f);
    client.balance_neutral();

    // --- Part 9: Mixed sequence (single-axis balance then composite pose) ---
    std::cout << "\n[Mixed: single-axis balance sequence then composite pose]" << std::endl;
    client.balance_sequence({
        {"balance_pitch", 12.0f, 0.8f, "dynamic"},  // pitch 12°
        {"balance_yaw", 15.0f, 0.8f, "dynamic"},    // yaw 15°
        {"balance_neutral", 0.0f, 0.5f, "dynamic"}, // reset
    });
    client.dynamic_pose(2.0f, 18.0f, 10.0f, 12.0f, -0.08f);
    client.balance_neutral();

    // --- Part 10: Rapid composite pose sequence (demonstrate min-to-max range) ---
    std::cout << "\n[Rapid composite pose sequence]" << std::endl;
    client.dynamic_pose(1.0f, 10.0f, 5.0f, 8.0f, -0.04f);
    client.static_pose(1.5f, -15.0f, -8.0f, -10.0f, -0.06f);
    client.dynamic_pose(3.0f, 25.0f, 12.0f, 18.0f, -0.10f);
    client.static_pose(5.0f, -30.0f, -15.0f, -20.0f, -0.12f);
    client.balance_neutral();

    std::cout << "\nDone." << std::endl;
    return 0;
}
