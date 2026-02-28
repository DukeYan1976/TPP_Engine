cmake_minimum_required(VERSION 3.10)
project(MockCAM)

set(CMAKE_CXX_STANDARD 11)

find_package(OpenCASCADE REQUIRED)

add_library(mock_cam SHARED
    mock_cam.cpp
    mock_cam.h
)

target_include_directories(mock_cam PRIVATE ${OpenCASCADE_INCLUDE_DIR})
target_link_libraries(mock_cam ${OpenCASCADE_LIBRARIES})

if(WIN32)
    target_compile_definitions(mock_cam PRIVATE MOCK_CAM_EXPORTS)
endif()

if(UNIX AND NOT APPLE)
    set_target_properties(mock_cam PROPERTIES
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON
    )
endif()

if(APPLE)
    set_target_properties(mock_cam PROPERTIES
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON
    )
endif()
