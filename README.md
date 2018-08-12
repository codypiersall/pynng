cffi bindings for Nanomsg

TODO
====

* Right now I'm modifying the CMake build file to set
  `CMAKE_POSITION_INDEPENDENT_CODE`.  This avoids problems when linking into
  the final .so file, but there is probably a better way to do it.
* Generating the API file is fragile, becuase it is not remotely C syntax
  aware; it's just dumb old sed.

