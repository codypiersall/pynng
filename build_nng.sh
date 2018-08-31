#! /bin/bash

# build the nng library
# do stuff in a subshell so we don't mess up the environment

if which ninja > /dev/null 2>/dev/null; then
    cmake_args=' -G Ninja '
fi

cmake_args="$cmake_args"

(
    git submodule update --init &&
    cd nng &&
    rm -rf build &&
    mkdir build &&
    cd build &&
    CFLAGS=-fPIC cmake $cmake_args .. &&
    CFLAGS=-fPIC cmake --build .

)
