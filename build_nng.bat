:: The Windows version of building the nng library
::
:: It is required to pass in the correct generator for CMake here, since
:: different versions of Python require different CMake generators.  The setup
:: script handles that automatically.
:: @echo off

pushd .
rmdir /s /q mbedtls
git clone --recursive https://github.com/ARMmbed/mbedtls.git
pushd mbedtls
git checkout %2
popd

mkdir mbedtls\build mbedtls\prefix
cd mbedtls\build

cmake %~3 -DENABLE_TESTING=OFF ^
-DENABLE_PROGRAMS=OFF -DCMAKE_BUILD_TYPE=Release ^
-DCMAKE_INSTALL_PREFIX=..\prefix ..
cmake --build . --config Release
cmake --install . --config Release

popd

pushd .
rmdir /s /q nng
git clone https://github.com/nanomsg/nng nng
pushd nng
git checkout %1
popd

mkdir nng\build
cd nng\build

cmake %~3 -DNNG_ENABLE_TLS=ON ^
-DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DCMAKE_BUILD_TYPE=Release ^
-DMBEDTLS_ROOT_DIR=%cd%/../../mbedtls/prefix/ ..

cmake --build . --config Release
popd
