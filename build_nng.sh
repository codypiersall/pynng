#!/bin/sh

# build the nng library
# do stuff in a subshell so we don't mess up the environment

if which ninja > /dev/null 2>/dev/null; then
    cmake_args=' -G Ninja '
fi

cmake_args="$cmake_args"

(
    if [ ! -e mbedtls ]; then
        git clone --recursive https://github.com/ARMmbed/mbedtls.git
        (
        cd mbedtls
        git checkout "$2"
        )
    fi
    cd mbedtls &&
    rm -rf build prefix &&
    mkdir build prefix &&
    cd build &&
    CFLAGS=-fPIC cmake $cmake_args -DENABLE_TESTING=OFF \
          -DENABLE_PROGRAMS=OFF -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=../prefix .. &&
    cmake --build . &&
    cmake --install .
)

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
    CFLAGS=-fPIC cmake $cmake_args -DNNG_ENABLE_TLS=ON \
          -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DCMAKE_BUILD_TYPE=Release \
          -DMBEDTLS_ROOT_DIR=$(pwd)/../../mbedtls/prefix/ .. &&
    cmake --build .
)
