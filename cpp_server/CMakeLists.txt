cmake_minimum_required(VERSION 3.10)
project(CppServer)

set(CMAKE_CXX_STANDARD 14)

find_package(gRPC CONFIG REQUIRED)
find_package(Protobuf REQUIRED)

include_directories(${CMAKE_SOURCE_DIR}/..)
include_directories(${CMAKE_SOURCE_DIR}/../mock_cam)

link_directories(${CMAKE_SOURCE_DIR}/../mock_cam/build)

add_executable(cam_server
    server.cpp
    ../cam_service.pb.cc
    ../cam_service.grpc.pb.cc
)

target_link_libraries(cam_server
    gRPC::grpc++
    protobuf::libprotobuf
    mock_cam
)

if(APPLE)
    set_target_properties(cam_server PROPERTIES
        BUILD_RPATH "${CMAKE_SOURCE_DIR}/../mock_cam/build"
        INSTALL_RPATH "${CMAKE_SOURCE_DIR}/../mock_cam/build"
    )
endif()

if(UNIX AND NOT APPLE)
    set_target_properties(cam_server PROPERTIES
        BUILD_RPATH "${CMAKE_SOURCE_DIR}/../mock_cam/build"
        INSTALL_RPATH "${CMAKE_SOURCE_DIR}/../mock_cam/build"
    )
endif()
