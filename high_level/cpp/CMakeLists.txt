cmake_minimum_required(VERSION 3.10)
project(grpc_client_examples)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(GRPC REQUIRED grpc++ grpc)
pkg_check_modules(PROTOBUF REQUIRED protobuf)

find_package(Threads REQUIRED)

find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin REQUIRED)

# 全局 include，确保 compile_commands.json 包含所有路径
# CMake 会吞掉系统路径（如 /usr/local/include），所以用 add_compile_options 强制写入
include_directories(
    ${CMAKE_CURRENT_BINARY_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}
)
if(GRPC_INCLUDE_DIRS)
    add_compile_options("-I${GRPC_INCLUDE_DIRS}")
endif()
if(PROTOBUF_INCLUDE_DIRS)
    add_compile_options("-I${PROTOBUF_INCLUDE_DIRS}")
endif()

set(PROTO_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}/proto")
set(PROTO_FILES grpc_service.proto)
set(PROTO_OUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/")
file(MAKE_DIRECTORY ${PROTO_OUT_DIR})

# cmake configure 时即生成 proto 文件，确保 clangd 能找到头文件
foreach(PROTO_FILE ${PROTO_FILES})
    get_filename_component(PROTO_NAME ${PROTO_FILE} NAME_WE)
    set(PROTO_SRC "${PROTO_OUT_DIR}/${PROTO_NAME}.pb.cc")
    set(PROTO_HDR "${PROTO_OUT_DIR}/${PROTO_NAME}.pb.h")
    set(GRPC_SRC "${PROTO_OUT_DIR}/${PROTO_NAME}.grpc.pb.cc")
    set(GRPC_HDR "${PROTO_OUT_DIR}/${PROTO_NAME}.grpc.pb.h")

    if(NOT EXISTS ${PROTO_HDR} OR NOT EXISTS ${GRPC_HDR})
        message(STATUS "Generating gRPC C++ code from ${PROTO_FILE} ...")
        execute_process(
            COMMAND protoc
                --cpp_out=${PROTO_OUT_DIR}
                --grpc_out=${PROTO_OUT_DIR}
                --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
                -I${PROTO_SRC_DIR}
                ${PROTO_SRC_DIR}/${PROTO_FILE}
            RESULT_VARIABLE PROTO_RESULT
        )
        if(NOT PROTO_RESULT EQUAL 0)
            message(FATAL_ERROR "Failed to generate gRPC code from ${PROTO_FILE}")
        endif()
    endif()

    # 增量构建时仍通过 custom_command 自动重新生成
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

    list(APPEND ALL_PROTO_SRCS ${PROTO_SRC} ${GRPC_SRC})
endforeach()

add_library(proto_lib STATIC ${ALL_PROTO_SRCS})
target_link_libraries(proto_lib PUBLIC
    ${GRPC_LIBRARIES}
    ${PROTOBUF_LIBRARIES}
    Threads::Threads
)

add_executable(e1_get_available_motions e1_get_available_motions.cpp)
target_link_libraries(e1_get_available_motions PRIVATE proto_lib)

add_executable(e2_get_current_state e2_get_current_state.cpp)
target_link_libraries(e2_get_current_state PRIVATE proto_lib)

add_executable(e3_auto_state_switch e3_auto_state_switch.cpp)
target_link_libraries(e3_auto_state_switch PRIVATE proto_lib)

add_executable(e4_velocity_sequence e4_velocity_sequence.cpp)
target_link_libraries(e4_velocity_sequence PRIVATE proto_lib)

add_executable(e5_robot_state e5_robot_state.cpp)
target_link_libraries(e5_robot_state PRIVATE proto_lib)

add_executable(e6_balance_motions e6_balance_motions.cpp)
target_link_libraries(e6_balance_motions PRIVATE proto_lib)

add_executable(e7_line_walk e7_line_walk.cpp)
target_link_libraries(e7_line_walk PRIVATE proto_lib)

add_executable(e8_rotation e8_rotation.cpp)
target_link_libraries(e8_rotation PRIVATE proto_lib)

add_executable(e9_combo_sequence e9_combo_sequence.cpp)
target_link_libraries(e9_combo_sequence PRIVATE proto_lib)

add_executable(e10_config_demo e10_config_demo.cpp)
target_link_libraries(e10_config_demo PRIVATE proto_lib)

add_executable(kill_robot kill_robot.cpp)
target_link_libraries(kill_robot PRIVATE proto_lib)