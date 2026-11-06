cmake_minimum_required(VERSION 3.20)
project(baseball LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
# __int128 is required; use Clang/GCC or the pinned Zig toolchain on Windows.
add_library(baseball SHARED native_bindings.cpp map.cpp)
