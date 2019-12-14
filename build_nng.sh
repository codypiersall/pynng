#!/bin/sh

set -e

NNG_REVISION=$1
MBEDTLS_REVISION=$2
CMAKE_ARGS=$3

CMAKE_CONFIG="--config Release"

#if not on MSYS2
if [ -z "$MSYSTEM" ] && ! [ "$TRAVIS_OS_NAME" == "windows" ]; then
	export CFLAGS=-fPIC
    CMAKE_CONFIG=""
fi

# last resort in the case of missing or old cmake (like manylinux docker)
if [ -e /.dockerenv ]; then
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    /opt/python/cp27-cp27m/bin/python get-pip.py
    /opt/python/cp27-cp27m/bin/pip install cmake
    ln -sf /opt/python/cp27-cp27m/bin/cmake /usr/bin/cmake
fi

cmake --version

(
    rm -rf mbedtls
    git clone --recursive https://github.com/ARMmbed/mbedtls.git
    (
        cd mbedtls
        git checkout "$MBEDTLS_REVISION"

        if [ "$(uname -s)" == "Linux" ]; then
            sed -i \
            's:#if defined(__i386__) && defined(__OPTIMIZE__):#if defined(__i386__) \&\& defined(__OPTIMIZE__) \&\& !defined(__PIC__):' \
            include/mbedtls/bn_mul.h
        fi
    )

    cd mbedtls
    mkdir build prefix
    cd build
    cmake $CMAKE_ARGS -DENABLE_TESTING=OFF \
          -DENABLE_PROGRAMS=OFF -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=../prefix ..
    cmake --build . $CMAKE_CONFIG

    if [ "$TRAVIS_OS_NAME" == "windows" ] || [ -n "$MSYSTEM" ] ; then
        cmake --install . $CMAKE_CONFIG
    else
        make install
    fi
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
    cmake --build . $CMAKE_CONFIG
)
