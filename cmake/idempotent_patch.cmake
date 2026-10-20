# Idempotent patch application script.
# Checks if the patch is already applied (reverse check), and if not,
# applies it with --ignore-whitespace for CRLF compatibility on Windows.
#
# Usage: cmake -DPATCH_FILE=/path/to/patch -P idempotent_patch.cmake

if(NOT PATCH_FILE)
  message(FATAL_ERROR "PATCH_FILE must be set")
endif()

# Check if the patch is already applied (reverse check succeeds)
execute_process(
  COMMAND git apply --reverse --check "${PATCH_FILE}"
  RESULT_VARIABLE _reverse_result
  OUTPUT_QUIET
  ERROR_QUIET
)

if(_reverse_result EQUAL 0)
  message(STATUS "Patch already applied: ${PATCH_FILE}")
else()
  # Apply the patch with whitespace tolerance for CRLF compatibility
  execute_process(
    COMMAND git apply --ignore-whitespace "${PATCH_FILE}"
    RESULT_VARIABLE _apply_result
  )
  if(NOT _apply_result EQUAL 0)
    message(FATAL_ERROR "Failed to apply patch: ${PATCH_FILE}")
  endif()
  message(STATUS "Applied patch: ${PATCH_FILE}")
endif()
