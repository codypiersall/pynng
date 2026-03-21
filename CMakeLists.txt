cmake_minimum_required(VERSION 3.26)
project(${SKBUILD_PROJECT_NAME} LANGUAGES C)

# ============================================
# Build Configuration
# ============================================

# Find Python development libraries
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module ${SKBUILD_SABI_COMPONENT})

# Set default build type to Release
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Choose the type of build" FORCE)
endif()

# Define build types
set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS "Debug" "Release")

# Enable position independent code
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Work around a bug in llvm-ranlib (all known versions as of LLVM 21.x) where
# it produces GNU ar format symbol tables when adding a symbol table to an
# archive with no exported symbols. CMake uses `ar qc` (no symbol table) then
# `ranlib` as separate steps, which triggers this: llvm-ranlib writes a GNU '/'
# entry instead of BSD '__.SYMDEF', and Apple's ld rejects it with:
#   ld: archive member '/' not a mach-o file
# This affects mbedTLS's libeverest.a and libp256m.a (zero exported symbols).
# The compiler and ar work fine; only ranlib is broken.
# See: https://github.com/llvm/llvm-project/issues/98997
if(APPLE AND CMAKE_RANLIB MATCHES "llvm-ranlib")
  find_program(_APPLE_RANLIB ranlib PATHS /usr/bin NO_DEFAULT_PATH)
  if(_APPLE_RANLIB)
    message(STATUS "Overriding llvm-ranlib with ${_APPLE_RANLIB} to avoid GNU archive format bug")
    set(CMAKE_RANLIB "${_APPLE_RANLIB}" CACHE FILEPATH "Ranlib" FORCE)
  endif()
endif()

# ============================================
# Dependencies Configuration
# ============================================

# Repository URLs and versions
set(NNG_REPO "https://github.com/nanomsg/nng" CACHE STRING "URL of the NNG repository")
set(NNG_REV "v1.11" CACHE STRING "Revision of NNG to use")

set(MBEDTLS_REPO "https://github.com/ARMmbed/mbedtls.git" CACHE STRING "URL of the mbedTLS repository")
set(MBEDTLS_REV "v3.6.3.1" CACHE STRING "Revision of mbedTLS to use")

# Function to download and build dependencies
include(FetchContent)

# ============================================
# MbedTLS Configuration
# ============================================

# Configure mbedTLS build options
set(ENABLE_PROGRAMS OFF CACHE BOOL "Build mbedTLS programs" FORCE)
set(ENABLE_TESTING OFF CACHE BOOL "Build mbedTLS tests" FORCE)
set(INSTALL_MBEDTLS OFF CACHE BOOL "Install mbedTLS" FORCE)
set(USE_STATIC_MBEDTLS_LIBRARY ON CACHE BOOL "Use static mbedtls libraries" FORCE)
set(USE_SHARED_MBEDTLS_LIBRARY OFF CACHE BOOL "Don't use shared mbedtls libraries" FORCE)
set(LINK_WITH_PTHREAD OFF CACHE BOOL "Don't link mbedtls with pthread" FORCE)
set(MBEDTLS_FATAL_WARNINGS OFF CACHE BOOL "Don't treat warnings as errors in mbedTLS" FORCE)

# Download mbedTLS
FetchContent_Declare(
  mbedtls
  GIT_REPOSITORY ${MBEDTLS_REPO}
  GIT_TAG ${MBEDTLS_REV}
  GIT_SHALLOW TRUE
)

# Make mbedTLS available
FetchContent_MakeAvailable(mbedtls)

# Disable installation for mbedTLS targets
foreach(_target mbedtls_static mbedx509_static mbedcrypto_static everest p256m)
  if(TARGET ${_target})
    set_target_properties(${_target} PROPERTIES EXCLUDE_FROM_ALL TRUE)
  endif()
endforeach()

# ============================================
# NNG Configuration
# ============================================

# Configure NNG build options
set(NNG_TESTS OFF CACHE BOOL "Build and run NNG tests" FORCE)
set(NNG_TOOLS OFF CACHE BOOL "Build NNG tools" FORCE)
set(NNG_ENABLE_TLS ON CACHE BOOL "Enable TLS transport" FORCE)
set(NNG_ENABLE_STATS OFF CACHE BOOL "Enable statistics" FORCE)
set(NNG_ENABLE_EXPORT OFF CACHE BOOL "Enable export functionality" FORCE)
set(NNG_INSTALL_MBEDTLS OFF CACHE BOOL "Do not install MbedTLS" FORCE)
set(NNG_ENABLE_NNGCAT OFF CACHE BOOL "Do not build nngcat" FORCE)
set(NNG_INSTALL_LIBS OFF CACHE BOOL "Do not install NNG libraries" FORCE)
set(NNG_INSTALL_HEADERS OFF CACHE BOOL "Do not install NNG headers" FORCE)
set(NNG_STATIC_LIB ON CACHE BOOL "Build static library" FORCE)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static libraries" FORCE)

# Set platform for NNG - macOS needs this
if(APPLE)
  set(NNG_PLATFORM "darwin" CACHE STRING "NNG platform" FORCE)
elseif(UNIX)
  set(NNG_PLATFORM "posix" CACHE STRING "NNG platform" FORCE)
elseif(WIN32)
  set(NNG_PLATFORM "windows" CACHE STRING "NNG platform" FORCE)
endif()

# Download NNG
# Patch fixes two issues not yet backported to NNG v1.x (v2.x has them on main):
#   1. mbedTLS 3.6.3 requires explicit mbedtls_ssl_set_hostname(NULL) call
#      when skipping hostname verification (CVE-2025-27809)
#   2. AIO task_abort race condition (upstream issue #2208)
# Remove this patch when upgrading to an NNG release that includes both fixes.
FetchContent_Declare(
  nng
  GIT_REPOSITORY ${NNG_REPO}
  GIT_TAG ${NNG_REV}
  GIT_SHALLOW TRUE
  PATCH_COMMAND git apply ${CMAKE_CURRENT_SOURCE_DIR}/patches/nng-mbedtls-hostname.patch
)

# ============================================
# Installation and Export Patching
# ============================================

# Override the install function to be selective
function(install)
  # Only allow installing our Python extension module and Python source files
  if(ARGV0 STREQUAL "TARGETS" AND ARGV1 STREQUAL "_nng")
    message(STATUS "Installing Python extension module: ${ARGV1}")
    message(STATUS "  Target destination: ${ARGV3}")
    message(STATUS "  Will be installed as: _nng${PYTHON_MODULE_SUFFIX}")
    _install(${ARGV})
  elseif(ARGV0 STREQUAL "DIRECTORY" AND ARGV1 MATCHES ".*pynng/")
    message(STATUS "Installing Python source files")
    _install(${ARGV})
  else()
    message(STATUS "Skipping install() for dependency: ${ARGV0} ${ARGV1}")
  endif()
endfunction()

# Completely disable the export command
function(export)
  message(STATUS "Skipping export() for NNG")
endfunction()

# Now use FetchContent_MakeAvailable to configure and build NNG
FetchContent_MakeAvailable(nng)

# ============================================
# CFFI Bindings Generation
# ============================================

# Define where the generated C file will be placed
set(CFFI_OUTPUT_FILE "${CMAKE_CURRENT_BINARY_DIR}/_nng.c")

# Create a custom command to generate the CFFI bindings
add_custom_command(
  OUTPUT ${CFFI_OUTPUT_FILE}
  COMMAND ${CMAKE_COMMAND} -E echo "Generating CFFI bindings for NNG..."
  COMMAND ${CMAKE_COMMAND} -E env "NNG_INCLUDE_DIR=${nng_SOURCE_DIR}/include"
    ${Python_EXECUTABLE} -m cffi_buildtool exec-python ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CFFI_OUTPUT_FILE} --ffi-var=ffibuilder
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py
  COMMENT "Generating CFFI bindings for NNG"
  VERBATIM
)

# ============================================
# Python Extension Module
# ============================================

# USE_SABI produces abi3-tagged wheels importable by Python 3.10+.
# PyPy doesn't support the stable ABI, so fall back to normal builds.
if(SKBUILD_SABI_COMPONENT)
  Python_add_library(_nng MODULE ${CFFI_OUTPUT_FILE} WITH_SOABI USE_SABI 3.10)
else()
  Python_add_library(_nng MODULE ${CFFI_OUTPUT_FILE} WITH_SOABI)
endif()

# Suppress incompatible-pointer-types errors in CFFI-generated code.
# The NNG API uses const-qualified pointer-to-pointer params (e.g. const nng_url **)
# but the generated CFFI cdef doesn't carry the const qualifier yet.
# TODO: Fix const handling in headerkit cdef writer and remove this workaround.
if(NOT MSVC)
  target_compile_options(_nng PRIVATE -Wno-incompatible-pointer-types)
endif()

# Include directories for Python and NNG headers
target_include_directories(_nng PRIVATE
  ${nng_SOURCE_DIR}/include
  ${Python_INCLUDE_DIRS})

# Link libraries
if(WIN32)
  target_link_libraries(_nng PRIVATE
    nng
    ${Python_LIBRARIES}
    Ws2_32
    Advapi32
    Bcrypt)
else()
  target_link_libraries(_nng PRIVATE
    nng
    ${Python_LIBRARIES}
    pthread)

  # Only link -latomic on Linux/non-Apple platforms. macOS provides atomic
  # intrinsics in the compiler runtime and has no libatomic. The universal2
  # cross-compilation also breaks CheckCSourceCompiles for this test.
  # See: https://github.com/codypiersall/pynng/issues/133
  if(NOT APPLE)
    include(CheckCSourceCompiles)
    check_c_source_compiles("
      #include <stdatomic.h>
      int main(void) {
        _Atomic long long x = 0;
        __atomic_fetch_add(&x, 1, __ATOMIC_SEQ_CST);
        return 0;
      }
    " HAVE_ATOMICS_WITHOUT_LIB)
    if(NOT HAVE_ATOMICS_WITHOUT_LIB)
      target_link_libraries(_nng PRIVATE atomic)
    endif()
  endif()
endif()

# ============================================
# Installation
# ============================================

# Install the Python `pynng` package
install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/pynng/
  DESTINATION ${SKBUILD_PROJECT_NAME}
  FILES_MATCHING
  PATTERN "*.py"
  PATTERN "__pycache__" EXCLUDE)

# Install the compiled `_nng` Python extension module
install(TARGETS _nng DESTINATION ${SKBUILD_PROJECT_NAME})
