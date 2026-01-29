cmake_minimum_required(VERSION 3.16)
project(DDSMiddlewareExamples LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS -pthread)

find_library(DDS_MIDDLEWARE_LIB dds_middleware 
    PATHS /usr/local/lib
    REQUIRED
)

include_directories(
    /usr/local/include
    /usr/local/include/ddscxx
    /usr/local/include/iceoryx/v2.0.0
)

find_package(CycloneDDS-CXX REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(OpenCV REQUIRED)

configure_file(./dds_config.yaml 
               ./config/dds_config.yaml 
               COPYONLY)

add_executable(e1_rgb_image_sub ./e1_rgb_image_sub.cc)
target_link_libraries(e1_rgb_image_sub  PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp ${OpenCV_LIBS})

add_executable(e2_depth_image_sub ./e2_depth_image_sub.cc)
target_link_libraries(e2_depth_image_sub  PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp ${OpenCV_LIBS})

add_executable(e3_led_control ./e3_led_control.cc)
target_link_libraries(e3_led_control PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e4_imu_state_sub ./e4_imu_state_sub.cc)
target_link_libraries(e4_imu_state_sub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e5_motor_state_sub ./e5_motor_state_sub.cc)
target_link_libraries(e5_motor_state_sub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e6_bms_state_sub ./e6_bms_state_sub.cc)
target_link_libraries(e6_bms_state_sub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e7_voice_pub ./e7_voice_pub.cc)
target_link_libraries(e7_voice_pub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e8_voice_sub ./e8_voice_sub.cc)
target_link_libraries(e8_voice_sub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

add_executable(e9_motor_cmd_pub ./e9_motor_cmd_pub.cc)
target_link_libraries(e9_motor_cmd_pub PRIVATE ${DDS_MIDDLEWARE_LIB} CycloneDDS-CXX::ddscxx yaml-cpp)

message(STATUS "DDS Middleware library: ${DDS_MIDDLEWARE_LIB}")
message(STATUS "Examples configured successfully")