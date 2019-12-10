#!/bin/sh

set -e

NNG_REVISION=$1
MBEDTLS_REVISION=$2
CMAKE_ARGS=$3

#if not on MSYS2
if [ -z "$MSYSTEM" ]; then
	export CFLAGS=-fPIC
fi

(
    rm -rf mbedtls
    git clone --recursive https://github.com/ARMmbed/mbedtls.git
    (
        cd mbedtls
        git checkout "$MBEDTLS_REVISION"
    )

    cd mbedtls
    mkdir build prefix
    cd build
    cmake $CMAKE_ARGS -DENABLE_TESTING=OFF \
          -DENABLE_PROGRAMS=OFF -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=../prefix ..
    cmake --build . --config Release
    cmake --install . --config Release
)

(
    rm -rf nng
    git clone https://github.com/nanomsg/nng
    (
        cd nng
        git checkout "$NNG_REVISION"
    )

    cd nng
    mkdir build
    cd build
    cmake $CMAKE_ARGS -DNNG_ENABLE_TLS=ON \
          -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DCMAKE_BUILD_TYPE=Release \
          -DMBEDTLS_ROOT_DIR=$(pwd)/../../mbedtls/prefix/ ..
    cmake --build . --config Release
)
