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

# TLS engine selection: mbed (default), wolf, openssl (v2 only), or none.
# - mbed: Fetches and builds mbedTLS from source (works with v1 and v2)
# - wolf: Fetches and builds wolfSSL from source (works with v1 and v2)
# - openssl: Uses system OpenSSL 3.5+ via find_package (v2 only; v1 built without TLS)
# - none: Disables TLS entirely
set(PYNNG_TLS_ENGINE "mbed" CACHE STRING "TLS engine to use (mbed, wolf, openssl, none)")
set_property(CACHE PYNNG_TLS_ENGINE PROPERTY STRINGS mbed wolf openssl none)

# ============================================
# Dependencies Configuration
# ============================================

# Repository URLs and versions
set(NNG_REPO "https://github.com/nanomsg/nng" CACHE STRING "URL of the NNG repository")
set(NNG_REV "v1.12.5" CACHE STRING "Revision of NNG to use")

set(MBEDTLS_REPO "https://github.com/ARMmbed/mbedtls.git" CACHE STRING "URL of the mbedTLS repository")
set(MBEDTLS_REV "v3.6.5" CACHE STRING "Revision of mbedTLS to use")

set(WOLFSSL_REPO "https://github.com/wolfSSL/wolfssl" CACHE STRING "URL of the wolfSSL repository")
set(WOLFSSL_REV "v5.8.0-stable" CACHE STRING "Revision of wolfSSL to use")

# v2-specific repository settings
set(NNG_V2_REPO "https://github.com/nanomsg/nng" CACHE STRING "URL of the NNG v2 repository")
set(NNG_V2_REV "v2.0.0" CACHE STRING "Revision of NNG v2 to use")

# Function to download and build dependencies
include(FetchContent)

# ============================================
# TLS Engine Configuration
# ============================================

# Validate engine choice
if(NOT PYNNG_TLS_ENGINE MATCHES "^(mbed|wolf|openssl|none)$")
  message(FATAL_ERROR "Invalid PYNNG_TLS_ENGINE '${PYNNG_TLS_ENGINE}'. Must be one of: mbed, wolf, openssl, none")
endif()

# Determine per-version TLS settings.
# NNG v1 supports: mbed, wolf, none
# NNG v2 supports: mbed, wolf, openssl, none
if(PYNNG_TLS_ENGINE STREQUAL "openssl")
  # OpenSSL is only supported by nng v2. v1 is built without TLS.
  message(STATUS "TLS engine: OpenSSL (v2 only; v1 will be built without TLS)")
  set(_V1_TLS_ENABLED OFF)
  set(_V1_TLS_ENGINE "none")
  set(_V2_TLS_ENABLED ON)
  set(_V2_TLS_ENGINE "openssl")
elseif(PYNNG_TLS_ENGINE STREQUAL "none")
  message(STATUS "TLS engine: disabled")
  set(_V1_TLS_ENABLED OFF)
  set(_V1_TLS_ENGINE "none")
  set(_V2_TLS_ENABLED OFF)
  set(_V2_TLS_ENGINE "none")
else()
  # mbed or wolf: supported by both v1 and v2
  message(STATUS "TLS engine: ${PYNNG_TLS_ENGINE}")
  set(_V1_TLS_ENABLED ON)
  set(_V1_TLS_ENGINE "${PYNNG_TLS_ENGINE}")
  set(_V2_TLS_ENABLED ON)
  set(_V2_TLS_ENGINE "${PYNNG_TLS_ENGINE}")
endif()

# --- mbedTLS ---
if(PYNNG_TLS_ENGINE STREQUAL "mbed")
  # Configure mbedTLS build options
  set(ENABLE_PROGRAMS OFF CACHE BOOL "Build mbedTLS programs" FORCE)
  set(ENABLE_TESTING OFF CACHE BOOL "Build mbedTLS tests" FORCE)
  set(INSTALL_MBEDTLS OFF CACHE BOOL "Install mbedTLS" FORCE)
  set(USE_STATIC_MBEDTLS_LIBRARY ON CACHE BOOL "Use static mbedtls libraries" FORCE)
  set(USE_SHARED_MBEDTLS_LIBRARY OFF CACHE BOOL "Don't use shared mbedtls libraries" FORCE)
  set(LINK_WITH_PTHREAD OFF CACHE BOOL "Don't link mbedtls with pthread" FORCE)
  set(MBEDTLS_FATAL_WARNINGS OFF CACHE BOOL "Don't treat warnings as errors in mbedTLS" FORCE)

  FetchContent_Declare(
    mbedtls
    GIT_REPOSITORY ${MBEDTLS_REPO}
    GIT_TAG ${MBEDTLS_REV}
    GIT_SHALLOW TRUE
  )
  FetchContent_MakeAvailable(mbedtls)

  # Disable installation for mbedTLS targets
  foreach(_target mbedtls_static mbedx509_static mbedcrypto_static everest p256m)
    if(TARGET ${_target})
      set_target_properties(${_target} PROPERTIES EXCLUDE_FROM_ALL TRUE)
    endif()
  endforeach()

  set(_TLS_LINK_LIBS mbedtls mbedx509 mbedcrypto)
endif()

# --- wolfSSL ---
if(PYNNG_TLS_ENGINE STREQUAL "wolf")
  set(WOLFSSL_EXAMPLES OFF CACHE BOOL "Build wolfSSL examples" FORCE)
  set(WOLFSSL_CRYPT_TESTS OFF CACHE BOOL "Build wolfSSL tests" FORCE)
  set(WOLFSSL_INSTALL OFF CACHE BOOL "Install wolfSSL" FORCE)
  set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static wolfSSL" FORCE)
  set(WOLFSSL_SNI ON CACHE BOOL "Enable SNI support" FORCE)
  set(WOLFSSL_SESSION_TICKET ON CACHE BOOL "Enable session tickets" FORCE)
  set(WOLFSSL_ALPN ON CACHE BOOL "Enable ALPN" FORCE)
  set(WOLFSSL_TLS13 ON CACHE BOOL "Enable TLS 1.3" FORCE)
  set(WOLFSSL_HARDEN ON CACHE BOOL "Enable hardening" FORCE)
  # Features required by nng's wolfSSL TLS engine:
  # - CRL: wolfSSL_CTX_LoadCRLBuffer
  # - OPENSSLEXTRA: wolfSSL_get_verify_result, wolfSSL_CTX_set_default_passwd_cb,
  #   wolfSSL_get_peer_certificate
  # - PSK: wolfSSL_CTX_get_psk_callback_ctx, wolfSSL_CTX_set_psk_*_callback
  set(WOLFSSL_CRL "yes" CACHE STRING "Enable CRL support" FORCE)
  set(WOLFSSL_OPENSSLEXTRA "yes" CACHE STRING "Enable OpenSSL compat layer" FORCE)
  set(WOLFSSL_PSK "yes" CACHE STRING "Enable PSK support" FORCE)
  # Disable stringop-overflow warning-as-error for wolfSSL. wolfSSL adds
  # -Werror to CMAKE_C_FLAGS, and GCC >= 12 triggers false positives for
  # stringop-overflow in wolfSSL's tls.c.
  set(_SAVED_CMAKE_C_FLAGS "${CMAKE_C_FLAGS}")
  if(CMAKE_C_COMPILER_ID STREQUAL "GNU")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wno-error=stringop-overflow")
  endif()

  FetchContent_Declare(
    wolfssl
    GIT_REPOSITORY ${WOLFSSL_REPO}
    GIT_TAG ${WOLFSSL_REV}
    GIT_SHALLOW TRUE
  )
  FetchContent_MakeAvailable(wolfssl)

  # Restore original C flags so they don't leak to other targets
  set(CMAKE_C_FLAGS "${_SAVED_CMAKE_C_FLAGS}")

  # Disable installation for wolfSSL targets
  if(TARGET wolfssl)
    set_target_properties(wolfssl PROPERTIES EXCLUDE_FROM_ALL TRUE)
  endif()

  # Pre-set wolfSSL feature detection results for nng v1.
  # nng's wolfssl CMakeLists.txt calls check_library_exists(wolfssl::wolfssl ...)
  # which uses try_compile — this fails because the wolfssl::wolfssl target
  # (from find_package) doesn't exist; we have a plain wolfssl target from
  # FetchContent instead. Setting these cache variables (matching the type and
  # value check_library_exists would produce) causes the macro to skip the check.
  set(NNG_WOLFSSL_HAVE_CRL 1 CACHE INTERNAL "Have library wolfssl")
  set(NNG_WOLFSSL_HAVE_VERIFY 1 CACHE INTERNAL "Have library wolfssl")
  set(NNG_WOLFSSL_HAVE_PASSWORD 1 CACHE INTERNAL "Have library wolfssl")
  set(NNG_WOLFSSL_HAVE_PEER_CERT 1 CACHE INTERNAL "Have library wolfssl")
  set(NNG_WOLFSSL_HAVE_DH 1 CACHE INTERNAL "Have library wolfssl")
  set(NNG_WOLFSSL_HAVE_PSK 1 CACHE INTERNAL "Have library wolfssl")

  set(_TLS_LINK_LIBS wolfssl)
endif()

# --- OpenSSL ---
if(PYNNG_TLS_ENGINE STREQUAL "openssl")
  find_package(OpenSSL 3.5 REQUIRED)
  set(_TLS_LINK_LIBS OpenSSL::SSL OpenSSL::Crypto)
endif()

# ============================================
# NNG Configuration
# ============================================

# Configure NNG build options
set(NNG_TESTS OFF CACHE BOOL "Build and run NNG tests" FORCE)
set(NNG_TOOLS OFF CACHE BOOL "Build NNG tools" FORCE)
set(NNG_ENABLE_TLS ${_V1_TLS_ENABLED} CACHE BOOL "Enable TLS transport" FORCE)
set(NNG_TLS_ENGINE "${_V1_TLS_ENGINE}" CACHE STRING "TLS engine for NNG v1" FORCE)
set(NNG_ENABLE_STATS ON CACHE BOOL "Enable statistics" FORCE)
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
FetchContent_Declare(
  nng
  GIT_REPOSITORY ${NNG_REPO}
  GIT_TAG ${NNG_REV}
  GIT_SHALLOW TRUE
)

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

# Convert TLS enabled booleans to 0/1 for Python env var
if(_V1_TLS_ENABLED)
  set(_V1_TLS_ENABLED_INT "1")
else()
  set(_V1_TLS_ENABLED_INT "0")
endif()

# Create a custom command to generate the CFFI bindings
add_custom_command(
  OUTPUT ${CFFI_OUTPUT_FILE}
  COMMAND ${CMAKE_COMMAND} -E echo "Generating CFFI bindings for NNG v1..."
  COMMAND ${CMAKE_COMMAND} -E env
    "NNG_INCLUDE_DIR=${nng_SOURCE_DIR}/include"
    "PYNNG_TLS_ENABLED=${_V1_TLS_ENABLED_INT}"
    ${Python_EXECUTABLE} -m cffi_buildtool exec-python ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CFFI_OUTPUT_FILE} --ffi-var=ffibuilder
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CMAKE_CURRENT_SOURCE_DIR}/src/aio_engine.h
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

# C11 standard is required for stdatomic.h in pynng's MPSC queue.
set_target_properties(_nng PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)

# Suppress incompatible-pointer-types errors in CFFI-generated code.
# The NNG API uses const-qualified pointer-to-pointer params (e.g. const nng_url **)
# but the generated CFFI cdef doesn't carry the const qualifier yet.
# TODO: Fix const handling in headerkit cdef writer and remove this workaround.
if(MSVC)
  target_compile_options(_nng PRIVATE /std:c11 /experimental:c11atomics)
else()
  target_compile_options(_nng PRIVATE -Wno-incompatible-pointer-types -fvisibility=hidden)
endif()

# Include directories for Python and NNG headers
target_include_directories(_nng PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/src
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
  if(POLICY CMP0169)
    cmake_policy(SET CMP0169 OLD)
  endif()
  FetchContent_Populate(nng_v2)
  if(POLICY CMP0169)
    cmake_policy(SET CMP0169 NEW)
  endif()

  # Determine the static library path based on platform
  if(WIN32)
    set(NNG_V2_STATIC_LIB "<INSTALL_DIR>/lib/nng.lib")
  else()
    set(NNG_V2_STATIC_LIB "<INSTALL_DIR>/lib/libnng.a")
  endif()

  # Define the install directory upfront as an absolute path.
  # ExternalProject_Get_Property(INSTALL_DIR) can return a relative path
  # when INSTALL_DIR isn't explicitly set, which breaks IMPORTED_LOCATION
  # in cross-compilation environments like cibuildwheel.
  set(NNG_V2_INSTALL_DIR "${CMAKE_CURRENT_BINARY_DIR}/nng_v2_install")

  # Common ExternalProject args for all TLS engines
  set(_NNG_V2_CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=<INSTALL_DIR>
    -DCMAKE_INSTALL_LIBDIR=lib
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DNNG_TESTS=OFF
    -DNNG_TOOLS=OFF
    -DNNG_ENABLE_TLS=${_V2_TLS_ENABLED}
    -DNNG_TLS_ENGINE=${_V2_TLS_ENGINE}
    -DNNG_ENABLE_STATS=ON
    -DNNG_ENABLE_NNGCAT=OFF
    -DBUILD_SHARED_LIBS=OFF
    -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
    -DCMAKE_RANLIB=${CMAKE_RANLIB}
  )
  set(_NNG_V2_CMAKE_CACHE_ARGS "")
  set(_NNG_V2_DEPENDS "")

  # --- TLS engine staging for v2 ExternalProject ---
  # ExternalProject builds in an isolated CMake context, so it can't use
  # FetchContent targets directly. We stage TLS libraries into a prefix
  # directory that the ExternalProject's find_package() can discover.

  if(_V2_TLS_ENGINE STREQUAL "mbed")
    # Stage mbedTLS headers and libraries for the v2 ExternalProject.
    set(MBEDTLS_STAGE_DIR "${CMAKE_CURRENT_BINARY_DIR}/mbedtls-stage")
    file(MAKE_DIRECTORY "${MBEDTLS_STAGE_DIR}/include")
    file(MAKE_DIRECTORY "${MBEDTLS_STAGE_DIR}/lib")

    file(COPY "${mbedtls_SOURCE_DIR}/include/mbedtls" DESTINATION "${MBEDTLS_STAGE_DIR}/include")
    file(COPY "${mbedtls_SOURCE_DIR}/include/psa" DESTINATION "${MBEDTLS_STAGE_DIR}/include")

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

    list(APPEND _NNG_V2_CMAKE_ARGS -DMBEDTLS_ROOT=${MBEDTLS_STAGE_DIR})
    # Pre-cache _MBEDTLS_V2_OR_NEWER to bypass FindMbedTLS.cmake's
    # check_symbol_exists(mbedtls_ssl_init) which fails when linking static
    # mbedTLS without -lpthread. We know mbedTLS 3.x has this symbol.
    list(APPEND _NNG_V2_CMAKE_CACHE_ARGS -D_MBEDTLS_V2_OR_NEWER:INTERNAL=TRUE)
    list(APPEND _NNG_V2_DEPENDS mbedtls_stage)

  elseif(_V2_TLS_ENGINE STREQUAL "wolf")
    # Stage wolfSSL headers and library for the v2 ExternalProject.
    set(WOLFSSL_STAGE_DIR "${CMAKE_CURRENT_BINARY_DIR}/wolfssl-stage")
    file(MAKE_DIRECTORY "${WOLFSSL_STAGE_DIR}/include")
    file(MAKE_DIRECTORY "${WOLFSSL_STAGE_DIR}/lib")

    file(COPY "${wolfssl_SOURCE_DIR}/wolfssl" DESTINATION "${WOLFSSL_STAGE_DIR}/include"
      FILES_MATCHING PATTERN "*.h")

    add_custom_target(wolfssl_stage ALL
      COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:wolfssl>" "${WOLFSSL_STAGE_DIR}/lib/"
      DEPENDS wolfssl
      COMMENT "Staging wolfSSL library for nng v2 build"
    )

    list(APPEND _NNG_V2_CMAKE_ARGS -DWOLFSSL_ROOT_DIR=${WOLFSSL_STAGE_DIR})
    list(APPEND _NNG_V2_DEPENDS wolfssl_stage)

  elseif(_V2_TLS_ENGINE STREQUAL "openssl")
    # OpenSSL is a system library; pass its location to ExternalProject.
    if(OPENSSL_ROOT_DIR)
      list(APPEND _NNG_V2_CMAKE_ARGS -DOPENSSL_ROOT_DIR=${OPENSSL_ROOT_DIR})
    endif()
  endif()

  ExternalProject_Add(nng_v2_build
    SOURCE_DIR ${nng_v2_SOURCE_DIR}
    PREFIX ${CMAKE_CURRENT_BINARY_DIR}/nng_v2_build-prefix
    INSTALL_DIR ${NNG_V2_INSTALL_DIR}
    DEPENDS ${_NNG_V2_DEPENDS}
    CMAKE_ARGS ${_NNG_V2_CMAKE_ARGS}
    CMAKE_CACHE_ARGS ${_NNG_V2_CMAKE_CACHE_ARGS}
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

  # Convert v2 TLS enabled boolean to 0/1 for Python env var
  if(_V2_TLS_ENABLED)
    set(_V2_TLS_ENABLED_INT "1")
  else()
    set(_V2_TLS_ENABLED_INT "0")
  endif()

  # The v2 CFFI generation depends on the v2 build completing (so headers are installed).
  add_custom_command(
    OUTPUT ${CFFI_V2_OUTPUT_FILE}
    COMMAND ${CMAKE_COMMAND} -E echo "Generating CFFI bindings for NNG v2..."
    COMMAND ${CMAKE_COMMAND} -E env
      "NNG_INCLUDE_DIR=${NNG_V2_INSTALL_DIR}/include"
      "NNG_MODULE_NAME=pynng._nng_v2"
      "PYNNG_TLS_ENABLED=${_V2_TLS_ENABLED_INT}"
      ${Python_EXECUTABLE} -m cffi_buildtool exec-python ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CFFI_V2_OUTPUT_FILE} --ffi-var=ffibuilder
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/build_pynng.py ${CMAKE_CURRENT_SOURCE_DIR}/src/aio_engine.h nng_v2_build
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

  # C11 standard is required for stdatomic.h in pynng's MPSC queue.
  set_target_properties(_nng_v2 PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)

  # Compile options for v2 extension
  if(MSVC)
    target_compile_options(_nng_v2 PRIVATE /std:c11 /experimental:c11atomics)
  else()
    target_compile_options(_nng_v2 PRIVATE -Wno-incompatible-pointer-types -fvisibility=hidden)
  endif()

  # Include directories
  target_include_directories(_nng_v2 PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${NNG_V2_INSTALL_DIR}/include
    ${Python_INCLUDE_DIRS})

  # Link libraries. nng v2's static lib has undefined TLS symbols, so we
  # link against the same TLS library we already built for v1 via FetchContent
  # (or the system OpenSSL if that engine was selected).
  # _TLS_LINK_LIBS is set during engine configuration above.
  if(WIN32)
    target_link_libraries(_nng_v2 PRIVATE
      nng_v2_imported
      ${_TLS_LINK_LIBS}
      ${Python_LIBRARIES}
      Ws2_32
      Advapi32
      Bcrypt)
  else()
    target_link_libraries(_nng_v2 PRIVATE
      nng_v2_imported
      ${_TLS_LINK_LIBS}
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
