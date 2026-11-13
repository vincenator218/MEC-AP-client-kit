cmake_minimum_required(VERSION 3.20)
project(mec_ap CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
  message(FATAL_ERROR "The game is 64-bit: configure an x64 build (Visual Studio: x64-Release).")
endif()

add_compile_definitions(WIN32_LEAN_AND_MEAN NOMINMAX UNICODE _UNICODE _CRT_SECURE_NO_WARNINGS)
if(MSVC)
  add_compile_options(/W4 /permissive- /utf-8)
  # one self-contained DLL: no Visual C++ redistributable needed on the player's PC
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
endif()

add_library(mec_ap SHARED
  src/dllmain.cpp
  src/apply.cpp
  src/build_check.cpp
  src/hooks.cpp
  src/listener.cpp
  src/link.cpp
  src/log.cpp)
target_link_libraries(mec_ap PRIVATE ws2_32)

add_executable(mec_ap_inject inject/mec_ap_inject.cpp)
