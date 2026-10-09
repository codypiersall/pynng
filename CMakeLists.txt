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
# Build Options
# ============================================

option(BUILD_NNG_V2 "Build nng v2 CFFI module alongside v1" ON)

# ============================================
# Dependencies Configuration
# ============================================

# Repository URLs and versions
set(NNG_REPO "https://github.com/nanomsg/nng" CACHE STRING "URL of the NNG repository")
set(NNG_REV "v1.11" CACHE STRING "Revision of NNG to use")

set(MBEDTLS_REPO "https://github.com/ARMmbed/mbedtls.git" CACHE STRING "URL of the mbedTLS repository")
set(MBEDTLS_REV "v3.6.5" CACHE STRING "Revision of mbedTLS to use")

# v2-specific repository settings
set(NNG_V2_REPO "https://github.com/nanomsg/nng" CACHE STRING "URL of the NNG v2 repository")
set(NNG_V2_REV "v2.0.0-alpha.7" CACHE STRING "Revision of NNG v2 to use")

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
#   1. mbedTLS 3.6.3+ requires explicit mbedtls_ssl_set_hostname(NULL) call
#      when skipping hostname verification (CVE-2025-27809)
#   2. AIO task_abort race condition (upstream issue #2208)
# Remove this patch when upgrading to an NNG release that includes both fixes.
if(NNG_REV STREQUAL "v1.11")
  FetchContent_Declare(
    nng
    GIT_REPOSITORY ${NNG_REPO}
    GIT_TAG ${NNG_REV}
    GIT_SHALLOW TRUE
    PATCH_COMMAND ${CMAKE_COMMAND}
      -DPATCH_FILE=${CMAKE_CURRENT_SOURCE_DIR}/patches/nng-mbedtls-hostname.patch
      -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/idempotent_patch.cmake
  )
else()
  FetchContent_Declare(
    nng
    GIT_REPOSITORY ${NNG_REPO}
    GIT_TAG ${NNG_REV}
    GIT_SHALLOW TRUE
  )
endif()

# ============================================
# Installation and Export Patching
# ============================================

# Override the install function to be selective
function(install)
  # Only allow installing our Python extension modules and Python source files
  if(ARGV0 STREQUAL "TARGETS" AND (ARGV1 STREQUAL "_nng" OR ARGV1 STREQUAL "_nng_v2"))
    message(STATUS "Installing Python extension module: ${ARGV1}")
    message(STATUS "  Target destination: ${ARGV3}")
    message(STATUS "  Will be installed as: ${ARGV1}${PYTHON_MODULE_SUFFIX}")
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
  target_compile_options(_nng PRIVATE -Wno-incompatible-pointer-types -fvisibility=hidden)
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
# NNG v2 Configuration (ExternalProject for target isolation)
# ============================================

if(BUILD_NNG_V2)
  include(ExternalProject)

  # Download nng v2 source via FetchContent (download only, no add_subdirectory).
  # We use FetchContent_Populate instead of FetchContent_MakeAvailable because
  # MakeAvailable would call add_subdirectory, causing a CMake target collision
  # with v1's "nng" target. The v2 source is built separately via ExternalProject.
  FetchContent_Declare(
    nng_v2
    GIT_REPOSITORY ${NNG_V2_REPO}
    GIT_TAG ${NNG_V2_REV}
    GIT_SHALLOW TRUE
  )
  cmake_policy(SET CMP0169 OLD)
  FetchContent_Populate(nng_v2)
  cmake_policy(SET CMP0169 NEW)

  # Determine the static library path based on platform
  if(WIN32)
    set(NNG_V2_STATIC_LIB "<INSTALL_DIR>/lib/nng.lib")
  else()
    set(NNG_V2_STATIC_LIB "<INSTALL_DIR>/lib/libnng.a")
  endif()

  # Stage mbedTLS headers and libraries so the v2 ExternalProject can find them.
  # The v1 build already fetched and built mbedTLS via FetchContent; we create a
  # staging directory that looks like an installed mbedTLS for find_package().
  set(MBEDTLS_STAGE_DIR "${CMAKE_CURRENT_BINARY_DIR}/mbedtls-stage")
  file(MAKE_DIRECTORY "${MBEDTLS_STAGE_DIR}/include")
  file(MAKE_DIRECTORY "${MBEDTLS_STAGE_DIR}/lib")

  # Copy headers at configure time (they exist after FetchContent_MakeAvailable)
  file(COPY "${mbedtls_SOURCE_DIR}/include/mbedtls" DESTINATION "${MBEDTLS_STAGE_DIR}/include")
  file(COPY "${mbedtls_SOURCE_DIR}/include/psa" DESTINATION "${MBEDTLS_STAGE_DIR}/include")

  # Create a custom target that stages the built mbedTLS libraries after they are compiled.
  # The libraries don't exist at configure time, so we copy them at build time.
  add_custom_target(mbedtls_stage ALL
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "$<TARGET_FILE:mbedtls>" "${MBEDTLS_STAGE_DIR}/lib/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "$<TARGET_FILE:mbedx509>" "${MBEDTLS_STAGE_DIR}/lib/"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
      "$<TARGET_FILE:mbedcrypto>" "${MBEDTLS_STAGE_DIR}/lib/"
    DEPENDS mbedtls mbedx509 mbedcrypto
    COMMENT "Staging mbedTLS libraries for nng v2 build"
  )

  # Build nng v2 in a completely isolated build tree via ExternalProject_Add.
  # This avoids CMake target name collision with v1 (both define a target "nng").
  # We pass MBEDTLS_ROOT so v2's find_package(MbedTLS) finds our staged copy.
  #
  # _MBEDTLS_V2_OR_NEWER is pre-cached to bypass FindMbedTLS.cmake's
  # check_symbol_exists(mbedtls_ssl_init) which fails when linking static
  # mbedTLS without -lpthread. We know mbedTLS 3.x has this symbol.
  # Define the install directory upfront as an absolute path.
  # ExternalProject_Get_Property(INSTALL_DIR) can return a relative path
  # when INSTALL_DIR isn't explicitly set, which breaks IMPORTED_LOCATION
  # in cross-compilation environments like cibuildwheel.
  set(NNG_V2_INSTALL_DIR "${CMAKE_CURRENT_BINARY_DIR}/nng_v2_install")

  ExternalProject_Add(nng_v2_build
    SOURCE_DIR ${nng_v2_SOURCE_DIR}
    PREFIX ${CMAKE_CURRENT_BINARY_DIR}/nng_v2_build-prefix
    INSTALL_DIR ${NNG_V2_INSTALL_DIR}
    DEPENDS mbedtls_stage
    CMAKE_ARGS
      -DCMAKE_INSTALL_PREFIX=<INSTALL_DIR>
      -DCMAKE_INSTALL_LIBDIR=lib
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON
      -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
      -DNNG_TESTS=OFF
      -DNNG_TOOLS=OFF
      -DNNG_ENABLE_TLS=ON
      -DNNG_ENABLE_STATS=OFF
      -DNNG_ENABLE_NNGCAT=OFF
      -DBUILD_SHARED_LIBS=OFF
      -DMBEDTLS_ROOT=${MBEDTLS_STAGE_DIR}
      -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
      -DCMAKE_RANLIB=${CMAKE_RANLIB}
    CMAKE_CACHE_ARGS
      -D_MBEDTLS_V2_OR_NEWER:INTERNAL=TRUE
    BUILD_BYPRODUCTS ${NNG_V2_STATIC_LIB}
  )

  add_library(nng_v2_imported STATIC IMPORTED)
  if(WIN32)
    set_target_properties(nng_v2_imported PROPERTIES
      IMPORTED_LOCATION "${NNG_V2_INSTALL_DIR}/lib/nng.lib"
    )
  else()
    set_target_properties(nng_v2_imported PROPERTIES
      IMPORTED_LOCATION "${NNG_V2_INSTALL_DIR}/lib/libnng.a"
    )
  endif()
  # Interface include dirs must exist at configure time for INTERFACE_INCLUDE_DIRECTORIES;
  # create the directory so CMake doesn't complain.
  file(MAKE_DIRECTORY "${NNG_V2_INSTALL_DIR}/include")
  set_target_properties(nng_v2_imported PROPERTIES
    INTERFACE_INCLUDE_DIRECTORIES "${NNG_V2_INSTALL_DIR}/include"
  )
  add_dependencies(nng_v2_imported nng_v2_build)

  # ============================================
  # v2 CFFI Bindings Generation
  # ============================================

  set(CFFI_V2_OUTPUT_FILE "${CMAKE_CURRENT_BINARY_DIR}/_nng_v2.c")

  # The v2 CFFI generation depends on the v2 build completing (so headers are installed).
  add_custom_command(
    OUTPUT ${CFFI_V2_OUTPUT_FILE}
    COMMAND ${CMAKE_COMMAND} -E echo "Generating CFFI bindings for NNG v2..."
    COMMAND ${CMAKE_COMMAND} -E env
      "NNG_INCLUDE_DIR=${NNG_V2_INSTALL_DIR}/include"
      "NNG_MODULE_NAME=pynng._nng_v2"
      ${Python_EXECUTABLE} -m cffi_buildtool exec-python ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CFFI_V2_OUTPUT_FILE} --ffi-var=ffibuilder
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py nng_v2_build
    COMMENT "Generating CFFI bindings for NNG v2"
    VERBATIM
  )

  # ============================================
  # v2 Python Extension Module
  # ============================================

  if(SKBUILD_SABI_COMPONENT)
    Python_add_library(_nng_v2 MODULE ${CFFI_V2_OUTPUT_FILE} WITH_SOABI USE_SABI 3.10)
  else()
    Python_add_library(_nng_v2 MODULE ${CFFI_V2_OUTPUT_FILE} WITH_SOABI)
  endif()

  # Compile options for v2 extension
  if(NOT MSVC)
    target_compile_options(_nng_v2 PRIVATE -Wno-incompatible-pointer-types -fvisibility=hidden)
  endif()

  # Include directories
  target_include_directories(_nng_v2 PRIVATE
    ${NNG_V2_INSTALL_DIR}/include
    ${Python_INCLUDE_DIRS})

  # Link libraries. nng v2's static lib has undefined mbedTLS symbols, so we
  # link against the same mbedTLS we already built for v1 via FetchContent.
  # mbedTLS target names: when only static is built (USE_SHARED_MBEDTLS_LIBRARY=OFF),
  # the targets are "mbedtls", "mbedx509", "mbedcrypto" (no _static suffix).
  if(WIN32)
    target_link_libraries(_nng_v2 PRIVATE
      nng_v2_imported
      mbedtls
      mbedx509
      mbedcrypto
      ${Python_LIBRARIES}
      Ws2_32
      Advapi32
      Bcrypt)
  else()
    target_link_libraries(_nng_v2 PRIVATE
      nng_v2_imported
      mbedtls
      mbedx509
      mbedcrypto
      ${Python_LIBRARIES}
      pthread)

    if(NOT APPLE)
      if(NOT DEFINED HAVE_ATOMICS_WITHOUT_LIB)
        include(CheckCSourceCompiles)
        check_c_source_compiles("
          #include <stdatomic.h>
          int main(void) {
            _Atomic long long x = 0;
            __atomic_fetch_add(&x, 1, __ATOMIC_SEQ_CST);
            return 0;
          }
        " HAVE_ATOMICS_WITHOUT_LIB)
      endif()
      if(NOT HAVE_ATOMICS_WITHOUT_LIB)
        target_link_libraries(_nng_v2 PRIVATE atomic)
      endif()
    endif()
  endif()

  # Install v2 extension module
  install(TARGETS _nng_v2 DESTINATION ${SKBUILD_PROJECT_NAME})
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
