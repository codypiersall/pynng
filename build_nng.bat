:: The Windows version of building the nng library
::
:: It is required to pass in the correct generator for CMake here, since
:: different versions of Python require different CMake generators.  The setup
:: script handles that automatically.
:: @echo off

if {%1}=={} (
    echo.ERROR: You must provide the correct CMake compiler generator.
    goto :end
)

pushd .
rmdir /s /q nng\build
git submodule update --init
mkdir nng\build
cd nng\build && ^
cmake -G %1 .. && ^
cmake --build . --config Release
popd

:end
