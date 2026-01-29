cmake_minimum_required(VERSION 3.10)
project(grpc_client_examples)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GRPC REQUIRED grpc++ grpc)
pkg_check_modules(PROTOBUF REQUIRED protobuf)

find_package(Threads REQUIRED)

find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

set(PROTO_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/proto")
set(PROTO_FILES grpc_service.proto)
# 生成的文件放在 build/proto/ 目录下，这样源码中的 #include "proto/xxx.h" 可以正常工作
set(PROTO_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/proto")
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
        COMMENT "Generating gRPC C++ code from ${PROTO_FILE}"
        VERBATIM
    )
endforeach()

add_library(proto_lib STATIC ${ALL_PROTO_SRCS})
target_include_directories(proto_lib PUBLIC 
    ${CMAKE_CURRENT_BINARY_DIR}  # 添加 build 目录，这样 "proto/xxx.h" 可以被找到
    ${GRPC_INCLUDE_DIRS}
    ${PROTOBUF_INCLUDE_DIRS}
)
target_link_libraries(proto_lib PUBLIC
    ${GRPC_LIBRARIES}
    ${PROTOBUF_LIBRARIES}
    Threads::Threads
)

add_executable(e1_get_available_motions e1_get_available_motions.cpp)
target_link_libraries(e1_get_available_motions PRIVATE proto_lib)

add_executable(e2_direct_state_switch e2_direct_state_switch.cpp)
target_link_libraries(e2_direct_state_switch PRIVATE proto_lib)

add_executable(e3_auto_state_switch e3_auto_state_switch.cpp)
target_link_libraries(e3_auto_state_switch PRIVATE proto_lib)

add_executable(e4_velocity_sequence e4_velocity_sequence.cpp)
target_link_libraries(e4_velocity_sequence PRIVATE proto_lib)

add_executable(e5_robot_state e5_robot_state.cpp)
target_link_libraries(e5_robot_state PRIVATE proto_lib)

add_executable(e6_balance_motions e6_balance_motions.cpp)
target_link_libraries(e6_balance_motions PRIVATE proto_lib)

add_executable(kill_robot kill_robot.cpp)
target_link_libraries(kill_robot PRIVATE proto_lib)