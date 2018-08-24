#! /bin/bash

# build the nng library
# do stuff in a subshell so we don't mess up the environment

if which ninja > /dev/null 2>/dev/null; then
    cmake_args=' -G Ninja '
fi

cmake_args="$cmake_args -DBUILD_SHARED_LIBS=on"

(
    git submodule update --init &&
    cd nng &&
    rm -rf build &&
    mkdir build &&
    cd build &&
    # intentionally not putting cmake_args in quotes!
    cmake $cmake_args .. &&
    cmake --build . &&
    # we built a shared library, but we actually didn't want a shared library,
    # we just wanted the position independent code compile option on all the
    # object files.  Now we're going to build the archive we link with.
    ar rcs libnng.a $(find src -name '*.o')

)
