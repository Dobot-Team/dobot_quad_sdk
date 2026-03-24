cmake_minimum_required(VERSION 3.14)
project(robot_client_tests)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Google Test via FetchContent (no manual install needed)
# ---------------------------------------------------------------------------
include(FetchContent)
FetchContent_Declare(
  googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.14.0
)
set(gtest_force_shared_crt ON CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(googletest)

# ---------------------------------------------------------------------------
# gRPC / Protobuf — reuse the same approach as ../cpp/CMakeLists.txt
# ---------------------------------------------------------------------------
find_package(PkgConfig REQUIRED)
pkg_check_modules(GRPC REQUIRED grpc++ grpc)
pkg_check_modules(PROTOBUF REQUIRED protobuf)
find_package(Threads REQUIRED)
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

# Proto sources live alongside the example cpp code
set(PROTO_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../cpp/proto")
set(PROTO_FILES grpc_service.proto)
set(PROTO_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/")
file(MAKE_DIRECTORY ${PROTO_OUT_DIR})

set(ALL_PROTO_SRCS)
foreach(PROTO_FILE ${PROTO_FILES})
    get_filename_component(PROTO_NAME ${PROTO_FILE} NAME_WE)
    set(PROTO_SRC "${PROTO_OUT_DIR}/${PROTO_NAME}.pb.cc")
    set(PROTO_HDR "${PROTO_OUT_DIR}/${PROTO_NAME}.pb.h")
    set(GRPC_SRC "${PROTO_OUT_DIR}/${PROTO_NAME}.grpc.pb.cc")
    set(GRPC_HDR "${PROTO_OUT_DIR}/${PROTO_NAME}.grpc.pb.h")
    list(APPEND ALL_PROTO_SRCS ${PROTO_SRC} ${GRPC_SRC})
    add_custom_command(
        OUTPUT ${PROTO_SRC} ${PROTO_HDR} ${GRPC_SRC} ${GRPC_HDR}
        COMMAND protoc
        ARGS --cpp_out=${PROTO_OUT_DIR}
             --grpc_out=${PROTO_OUT_DIR}
             --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
             -I${PROTO_SRC_DIR}
             ${PROTO_SRC_DIR}/${PROTO_FILE}
        DEPENDS ${PROTO_SRC_DIR}/${PROTO_FILE}
        COMMENT "Generating gRPC C++ code for tests"
        VERBATIM
    )
endforeach()

add_library(test_proto_lib STATIC ${ALL_PROTO_SRCS})
target_include_directories(test_proto_lib PUBLIC
    ${CMAKE_CURRENT_BINARY_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../../cpp   # for robot_client.h
    ${GRPC_INCLUDE_DIRS}
    ${PROTOBUF_INCLUDE_DIRS}
)
target_link_libraries(test_proto_lib PUBLIC
    ${GRPC_LIBRARIES}
    ${PROTOBUF_LIBRARIES}
    Threads::Threads
)

# ---------------------------------------------------------------------------
# Test executable
# ---------------------------------------------------------------------------
enable_testing()

add_executable(test_robot_client test_robot_client.cpp)
target_link_libraries(test_robot_client PRIVATE
    test_proto_lib
    GTest::gtest_main
)

include(GoogleTest)
gtest_discover_tests(test_robot_client)
