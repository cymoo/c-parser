cmake_minimum_required(VERSION 3.14)
project(test C)

set(CMAKE_EXPORT_COMPILE_COMMANDS on)
set(CMAKE_C_STANDARD 11)

add_executable(main main.c)
