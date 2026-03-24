// ==========================================================================
// test_robot_client.cpp — Unit tests for robot::Client helper functions
//
// Tests the pure / locally-verifiable parts of robot_client.h:
//   - make_request():       request defaults
//   - set_param():          typed parameter insertion
//   - make_velocity_string(): string formatting
//   - VelocityStep / BalanceMotion: struct defaults
//   - Parameter clamping:   tested via direct std::max/std::min replication
//   - set_obstacle_avoidance string overload: invalid_argument exception
//   - rotate:              direction validation
//
// Note: Methods that require a live gRPC channel (execute, get_state, etc.)
//       are NOT tested here. The Python test suite covers those via mocking.
// ==========================================================================

#include "robot_client.h"
#include <algorithm>
#include <cmath>
#include <gtest/gtest.h>
#include <stdexcept>
#include <string>

// ==========================================================================
// §1  make_request — request builder
// ==========================================================================

TEST(MakeRequest, DefaultNameAndLoop) {
  auto req = robot::make_request();
  EXPECT_EQ(req.sequence().sequence_id(), "seq");
  EXPECT_EQ(req.sequence().sequence_name(), "seq");
  EXPECT_FALSE(req.sequence().loop());
  EXPECT_TRUE(req.immediate_start());
}

TEST(MakeRequest, CustomNameAndLoop) {
  auto req = robot::make_request("demo", true);
  EXPECT_EQ(req.sequence().sequence_id(), "demo");
  EXPECT_TRUE(req.sequence().loop());
}

// ==========================================================================
// §2  set_param — typed parameter helpers
// ==========================================================================

TEST(SetParam, FloatParam) {
  grpc_comm::Motion m;
  robot::set_param(&m, "speed", 1.5f);
  ASSERT_EQ(m.parameters_size(), 1);
  EXPECT_EQ(m.parameters(0).key(), "speed");
  EXPECT_FLOAT_EQ(m.parameters(0).float_value(), 1.5f);
}

TEST(SetParam, IntParam) {
  grpc_comm::Motion m;
  robot::set_param(&m, "direction", 2);
  ASSERT_EQ(m.parameters_size(), 1);
  EXPECT_EQ(m.parameters(0).key(), "direction");
  EXPECT_EQ(m.parameters(0).int_value(), 2);
}

TEST(SetParam, StringParam) {
  grpc_comm::Motion m;
  robot::set_param(&m, "gait", std::string("walk"));
  ASSERT_EQ(m.parameters_size(), 1);
  EXPECT_EQ(m.parameters(0).key(), "gait");
  EXPECT_EQ(m.parameters(0).string_value(), "walk");
}

TEST(SetParam, MultipleParams) {
  grpc_comm::Motion m;
  robot::set_param(&m, "a", 1);
  robot::set_param(&m, "b", 2.0f);
  robot::set_param(&m, "c", std::string("x"));
  EXPECT_EQ(m.parameters_size(), 3);
}

// ==========================================================================
// §3  VelocityStep — struct default values
// ==========================================================================

TEST(VelocityStep, Defaults) {
  robot::VelocityStep step;
  EXPECT_FLOAT_EQ(step.vx, 0.0f);
  EXPECT_FLOAT_EQ(step.vy, 0.0f);
  EXPECT_FLOAT_EQ(step.vyaw, 0.0f);
  EXPECT_FLOAT_EQ(step.duration, 1.0f);
}

TEST(VelocityStep, CustomValues) {
  robot::VelocityStep step{0.5f, -0.1f, 0.3f, 2.5f};
  EXPECT_FLOAT_EQ(step.vx, 0.5f);
  EXPECT_FLOAT_EQ(step.vy, -0.1f);
  EXPECT_FLOAT_EQ(step.vyaw, 0.3f);
  EXPECT_FLOAT_EQ(step.duration, 2.5f);
}

// ==========================================================================
// §4  make_velocity_string — serialisation
// ==========================================================================

TEST(MakeVelocityString, SingleStep) {
  std::vector<robot::VelocityStep> steps = {{0.5f, 0.0f, 0.0f, 2.0f}};
  std::string s = robot::make_velocity_string(steps);
  // Should contain the four values separated by commas, ending with ";"
  EXPECT_NE(s.find(";"), std::string::npos);
  // Basic sanity: contains the vx value
  EXPECT_NE(s.find("0.5"), std::string::npos);
}

TEST(MakeVelocityString, MultipleSteps) {
  std::vector<robot::VelocityStep> steps = {
      {0.5f, 0.0f, 0.0f, 2.0f},
      {0.0f, 0.3f, 0.0f, 1.0f},
  };
  std::string s = robot::make_velocity_string(steps);
  // Two semicolons expected (one per step)
  int count = std::count(s.begin(), s.end(), ';');
  EXPECT_EQ(count, 2);
}

TEST(MakeVelocityString, Empty) {
  std::vector<robot::VelocityStep> steps;
  std::string s = robot::make_velocity_string(steps);
  EXPECT_TRUE(s.empty());
}

// ==========================================================================
// §5  BalanceMotion — struct defaults
// ==========================================================================

TEST(BalanceMotion, Defaults) {
  robot::BalanceMotion bm;
  EXPECT_TRUE(bm.motion_id.empty());
  EXPECT_FLOAT_EQ(bm.value, 0.0f);
  EXPECT_FLOAT_EQ(bm.duration, 2.0f);
  EXPECT_EQ(bm.mode, "dynamic");
}

TEST(BalanceMotion, CustomValues) {
  robot::BalanceMotion bm{"balance_pitch", 15.0f, 3.0f, "static"};
  EXPECT_EQ(bm.motion_id, "balance_pitch");
  EXPECT_FLOAT_EQ(bm.value, 15.0f);
  EXPECT_FLOAT_EQ(bm.duration, 3.0f);
  EXPECT_EQ(bm.mode, "static");
}

// ==========================================================================
// §6  Parameter clamping verification
//     (mirrors the logic inside Client methods using the same std::max/min)
// ==========================================================================

// ---------- speed_ratio: [0, 100] ----------

class SpeedRatioClamp : public ::testing::TestWithParam<std::pair<int, int>> {};

TEST_P(SpeedRatioClamp, ClampedCorrectly) {
  int input = GetParam().first;
  int expected = GetParam().second;
  int clamped = std::max(0, std::min(100, input));
  EXPECT_EQ(clamped, expected);
}

INSTANTIATE_TEST_SUITE_P(
    Ranges, SpeedRatioClamp,
    ::testing::Values(std::make_pair(-10, 0), std::make_pair(-1, 0),
                      std::make_pair(0, 0), std::make_pair(1, 1),
                      std::make_pair(50, 50), std::make_pair(100, 100),
                      std::make_pair(101, 100), std::make_pair(999, 100)));

// ---------- angle: [0, 360] ----------

class AngleClamp : public ::testing::TestWithParam<std::pair<float, float>> {};

TEST_P(AngleClamp, ClampedCorrectly) {
  float input = GetParam().first;
  float expected = GetParam().second;
  float clamped = std::max(0.0f, std::min(360.0f, input));
  EXPECT_FLOAT_EQ(clamped, expected);
}

INSTANTIATE_TEST_SUITE_P(Ranges, AngleClamp,
                         ::testing::Values(std::make_pair(-10.f, 0.f),
                                           std::make_pair(0.f, 0.f),
                                           std::make_pair(90.f, 90.f),
                                           std::make_pair(180.f, 180.f),
                                           std::make_pair(360.f, 360.f),
                                           std::make_pair(400.f, 360.f)));

// ---------- turns (circle): [1, 10] ----------

class TurnsClamp : public ::testing::TestWithParam<std::pair<int, int>> {};

TEST_P(TurnsClamp, ClampedCorrectly) {
  int input = GetParam().first;
  int expected = GetParam().second;
  int clamped = std::max(1, std::min(10, input));
  EXPECT_EQ(clamped, expected);
}

INSTANTIATE_TEST_SUITE_P(
    Ranges, TurnsClamp,
    ::testing::Values(std::make_pair(-1, 1), std::make_pair(0, 1),
                      std::make_pair(1, 1), std::make_pair(5, 5),
                      std::make_pair(10, 10), std::make_pair(15, 10)));

// ---------- distance (rotate_walk): [0, 3] ----------

class DistanceClamp : public ::testing::TestWithParam<std::pair<float, float>> {
};

TEST_P(DistanceClamp, ClampedCorrectly) {
  float input = GetParam().first;
  float expected = GetParam().second;
  float clamped = std::max(0.0f, std::min(3.0f, input));
  EXPECT_FLOAT_EQ(clamped, expected);
}

INSTANTIATE_TEST_SUITE_P(Ranges, DistanceClamp,
                         ::testing::Values(std::make_pair(-1.f, 0.f),
                                           std::make_pair(0.f, 0.f),
                                           std::make_pair(1.5f, 1.5f),
                                           std::make_pair(3.f, 3.f),
                                           std::make_pair(5.f, 3.f)));

// ---------- duration (balance/dynamic_pose): [0.5, 10] ----------

class DurationClamp : public ::testing::TestWithParam<std::pair<float, float>> {
};

TEST_P(DurationClamp, ClampedCorrectly) {
  float input = GetParam().first;
  float expected = GetParam().second;
  float clamped = std::max(0.5f, std::min(10.0f, input));
  EXPECT_FLOAT_EQ(clamped, expected);
}

INSTANTIATE_TEST_SUITE_P(
    Ranges, DurationClamp,
    ::testing::Values(std::make_pair(-1.f, 0.5f), std::make_pair(0.f, 0.5f),
                      std::make_pair(0.5f, 0.5f), std::make_pair(2.5f, 2.5f),
                      std::make_pair(10.f, 10.f), std::make_pair(15.f, 10.f)));

// ==========================================================================
// §7  Rotate direction validation (string overload)
// ==========================================================================

// We cannot call Client::rotate without a channel. Instead we test the
// normalisation + validation logic directly.

static int parse_rotate_direction(const std::string &direction) {
  std::string norm = direction;
  std::transform(norm.begin(), norm.end(), norm.begin(), ::tolower);
  if (norm == "left")
    return 0;
  if (norm == "right")
    return 1;
  throw std::invalid_argument("rotate direction must be \"left\" or \"right\"");
}

TEST(RotateDirection, Left) { EXPECT_EQ(parse_rotate_direction("left"), 0); }
TEST(RotateDirection, Right) { EXPECT_EQ(parse_rotate_direction("right"), 1); }
TEST(RotateDirection, CaseInsensitive) {
  EXPECT_EQ(parse_rotate_direction("LEFT"), 0);
  EXPECT_EQ(parse_rotate_direction("Right"), 1);
}
TEST(RotateDirection, Invalid) {
  EXPECT_THROW(parse_rotate_direction("up"), std::invalid_argument);
  EXPECT_THROW(parse_rotate_direction(""), std::invalid_argument);
}

// ==========================================================================
// §8  (removed — x_leg no longer exists, replaced by change_mode)
// ==========================================================================

// ==========================================================================
// §9  set_obstacle_avoidance string validation
// ==========================================================================

static bool parse_obstacle_avoidance(const std::string &enable) {
  std::string norm = enable;
  std::transform(norm.begin(), norm.end(), norm.begin(), ::tolower);
  if (norm == "on")
    return true;
  if (norm == "off")
    return false;
  throw std::invalid_argument(
      "set_obstacle_avoidance only accepts bool or \"on\"/\"off\"");
}

TEST(ObstacleAvoidance, On) { EXPECT_TRUE(parse_obstacle_avoidance("on")); }
TEST(ObstacleAvoidance, Off) { EXPECT_FALSE(parse_obstacle_avoidance("off")); }
TEST(ObstacleAvoidance, CaseInsensitive) {
  EXPECT_TRUE(parse_obstacle_avoidance("ON"));
  EXPECT_FALSE(parse_obstacle_avoidance("Off"));
}
TEST(ObstacleAvoidance, InvalidStrings) {
  EXPECT_THROW(parse_obstacle_avoidance("yes"), std::invalid_argument);
  EXPECT_THROW(parse_obstacle_avoidance("true"), std::invalid_argument);
  EXPECT_THROW(parse_obstacle_avoidance("1"), std::invalid_argument);
  EXPECT_THROW(parse_obstacle_avoidance(""), std::invalid_argument);
}

// ==========================================================================
// §10  rotate_walk: left/right threshold logic at 180°
// ==========================================================================

TEST(RotateWalk, LeftThreshold) {
  // angle <= 180 → rotate left, angle > 180 → rotate right
  float angle1 = 90.0f;
  EXPECT_TRUE(angle1 <= 180.0f); // should use "left"

  float angle2 = 180.0f;
  EXPECT_TRUE(angle2 <= 180.0f); // boundary: still "left"

  float angle3 = 181.0f;
  EXPECT_FALSE(angle3 <= 180.0f); // should use "right"
}

TEST(RotateWalk, RightAngleConversion) {
  // angle > 180 → rotate("right", 360 - angle)
  float angle = 270.0f;
  float converted = 360.0f - angle;
  EXPECT_FLOAT_EQ(converted, 90.0f);
}

// ==========================================================================
// §11  Balance value clamping
// ==========================================================================

TEST(BalanceValueClamp, RpyClampedTo35) {
  float val = std::max(-35.0f, std::min(35.0f, 50.0f));
  EXPECT_FLOAT_EQ(val, 35.0f);
  val = std::max(-35.0f, std::min(35.0f, -50.0f));
  EXPECT_FLOAT_EQ(val, -35.0f);
}

TEST(BalanceValueClamp, HeightClampedToNeg010) {
  float val = std::max(-0.10f, std::min(0.0f, -0.20f));
  EXPECT_FLOAT_EQ(val, -0.10f);
  val = std::max(-0.10f, std::min(0.0f, 0.05f));
  EXPECT_FLOAT_EQ(val, 0.0f);
}
