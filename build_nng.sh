#!/bin/sh

# build the nng library
# do stuff in a subshell so we don't mess up the environment

if which ninja > /dev/null 2>/dev/null; then
    cmake_args=' -G Ninja '
fi

cmake_args="$cmake_args"

(
    if [ ! -e nng ]; then
        git clone https://github.com/nanomsg/nng
        (
        cd nng
        git checkout "$1"
        )
    fi
    cd nng &&
    rm -rf build &&
    mkdir build &&
    cd build &&
    CFLAGS=-fPIC cmake $cmake_args .. &&
    CFLAGS=-fPIC cmake --build .

)
