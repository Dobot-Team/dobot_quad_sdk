#!/usr/bin/env python3
"""Example 1: List all available motions and their parameters."""
import sys
from dobot_quad import RobotClient


def main():
    robot = RobotClient(sys.argv[1] if len(sys.argv) > 1 else "192.168.5.2:50051")
    res = robot.get_motions()

    if not res.success:
        print(f"Failed: {res.message}")
        return 1

    print(f"Available motions ({len(res.motions)}):\n")
    for m in res.motions:
        desc = res.descriptions.get(m.motion_id, "")
        print(f"  [{m.motion_id}] {desc}")
        for p in m.parameters:
            val = (
                p.float_value if p.HasField("float_value") else p.int_value
                if p.HasField("int_value") else f'"{p.string_value}"' if p.HasField("string_value")
                else p.bool_value if p.HasField("bool_value") else "(unset)"
            )
            print(f"      {p.key}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
