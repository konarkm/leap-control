cmake_minimum_required(VERSION 3.20)

project(leap_probe C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

set(DEFAULT_LEAPSDK_PATHS
    "/Applications/Ultraleap Hand Tracking.app/Contents/LeapSDK"
    "/Applications/Ultraleap Hand Tracking Service.app/Contents/LeapSDK"
)

if(DEFINED ENV{LEAPSDK_INSTALL_LOCATION} AND NOT "$ENV{LEAPSDK_INSTALL_LOCATION}" STREQUAL "")
    set(LEAPSDK_ROOT "$ENV{LEAPSDK_INSTALL_LOCATION}")
else()
    foreach(candidate IN LISTS DEFAULT_LEAPSDK_PATHS)
        if(EXISTS "${candidate}/include/LeapC.h")
            set(LEAPSDK_ROOT "${candidate}")
            break()
        endif()
    endforeach()
endif()

if(NOT LEAPSDK_ROOT)
    message(FATAL_ERROR
        "Could not find LeapSDK. Set LEAPSDK_INSTALL_LOCATION or install Ultraleap Hand Tracking.")
endif()

message(STATUS "Using LeapSDK at ${LEAPSDK_ROOT}")

add_executable(leap_probe
    src/main.c
)

target_include_directories(leap_probe PRIVATE
    "${LEAPSDK_ROOT}/include"
)

target_link_directories(leap_probe PRIVATE
    "${LEAPSDK_ROOT}/lib"
)

target_link_libraries(leap_probe PRIVATE
    LeapC
    "-framework CoreFoundation"
)

set_target_properties(leap_probe PROPERTIES
    BUILD_RPATH "${LEAPSDK_ROOT}/lib"
)
