import pynng
import pynng.sockaddr
import pynng.tls


def _resolve_lib_ffi(py_obj):
    """Resolve the lib and ffi from a pynng object instance.

    Objects have _lib and _ffi attributes (directly on Sockets, or via
    properties that delegate to their socket on Dialer/Listener/Pipe/Context).

    Falls back to pynng.lib / pynng.ffi for backward compatibility.
    """
    _lib = getattr(py_obj, '_lib', None)
    _ffi = getattr(py_obj, '_ffi', None)
    if _lib is None:
        _lib = pynng.lib
    if _ffi is None:
        _ffi = pynng.ffi
    return _lib, _ffi


def _get_inst_and_func(py_obj, option_type, get_or_set):
    """
    Given the Python wrapper for one of nng's object types, return a tuple of
    (nng_object, nng_function).  This is only an _internal_ function.

    Args:
        py_obj Union(pynng.Socket, pynng.Dialer, pynng.Listener): the Python wrapper of
          the library type.
        option_type (str): The type of option.

    Returns:
        The tuple (nng_object, nng_func) for use in the module-level getopt*,
            setopt* functions

    """
    # Import base classes to avoid circular import issues at module level.
    # These are used for isinstance checks so they work with both v1 and v2.
    from . import _base

    _lib, _ffi = _resolve_lib_ffi(py_obj)

    # nng option getter/setter functions are all named in the same consistent manner.
    # The form is: nng_{nng_type}_{access_method}_{option_type}
    #
    # Where:
    # * lib_type is "socket", "dialer", "listener", "pipe", or "ctx";
    # * access_method is "get" or "set";
    # * option_type is "bool", "int", "ms", "size", "uint64", "ptr", or "string"
    #
    # we can figure out which method to call based on the py_obj (Socket, Dialer,
    # etc.), whether we are getting or settting, and

    if isinstance(py_obj, _base.Socket):
        name = "socket"
        obj = py_obj.socket
    elif isinstance(py_obj, _base.Dialer):
        name = "dialer"
        obj = py_obj.dialer
    elif isinstance(py_obj, _base.Listener):
        name = "listener"
        obj = py_obj.listener
    elif isinstance(py_obj, _base.Pipe):
        name = "pipe"
        obj = py_obj.pipe
    elif isinstance(py_obj, _base.Context):
        name = "ctx"
        obj = py_obj.context
    else:
        raise TypeError(f'The type "{type(py_obj)}" is not supported')

    if option_type:
        function_name = f"nng_{name}_{get_or_set}_{option_type}"
    else:
        # opaque get/set
        function_name = f"nng_{name}_{get_or_set}"
    nng_func = getattr(_lib, function_name)
    return obj, nng_func


def _getopt_int(obj, option):
    """Gets the specified option"""
    _lib, _ffi = _resolve_lib_ffi(obj)
    from ._base import to_char
    i = _ffi.new("int []", 1)
    opt_as_char = to_char(option, ffi=_ffi)
    nng_obj, lib_func = _get_inst_and_func(obj, "int", "get")
    # attempt to accept floats that are exactly int
    ret = lib_func(nng_obj, opt_as_char, i)
    pynng.check_err(ret)
    return i[0]


def _setopt_int(py_obj, option, value):
    """Sets the specified option to the specified value"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = "Invalid value {} of type {}.  Expected int."
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    obj, lib_func = _get_inst_and_func(py_obj, "int", "set")
    value = int(value)
    err = lib_func(obj, opt_as_char, value)
    pynng.check_err(err)


def _getopt_size(py_obj, option):
    """Gets the specified size option"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    i = _ffi.new("size_t []", 1)
    opt_as_char = to_char(option, ffi=_ffi)
    # attempt to accept floats that are exactly int
    obj, lib_func = _get_inst_and_func(py_obj, "size", "get")
    ret = lib_func(obj, opt_as_char, i)
    pynng.check_err(ret)
    return i[0]


def _setopt_size(py_obj, option, value):
    """Sets the specified size option to the specified value"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = "Invalid value {} of type {}.  Expected int."
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, "size", "set")
    err = lib_func(obj, opt_as_char, value)
    pynng.check_err(err)


def _getopt_ms(py_obj, option):
    """Gets the specified option"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    ms = _ffi.new("nng_duration []", 1)
    opt_as_char = to_char(option, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "ms", "get")
    ret = lib_func(obj, opt_as_char, ms)
    pynng.check_err(ret)
    return ms[0]


def _setopt_ms(py_obj, option, value):
    """Sets the specified option to the specified value"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    # attempt to accept floats that are exactly int (duration types are
    # just integers)
    if not int(value) == value:
        msg = "Invalid value {} of type {}.  Expected int."
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, "ms", "set")
    err = lib_func(obj, opt_as_char, value)
    pynng.check_err(err)


def _getopt_string(py_obj, option):
    """Gets the specified string option"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt = _ffi.new("char *[]", 1)
    opt_as_char = to_char(option, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "string", "get")
    ret = lib_func(obj, opt_as_char, opt)
    pynng.check_err(ret)
    py_string = _ffi.string(opt[0]).decode()
    _lib.nng_strfree(opt[0])
    return py_string


def _setopt_string(py_obj, option, value):
    """Sets the specified option to the specified value"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    val_as_char = to_char(value, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "string", "set")
    ret = lib_func(obj, opt_as_char, val_as_char)
    pynng.check_err(ret)


def _setopt_string_nonnull(py_obj, option, value):
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    val_as_char = to_char(value, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "", "set")
    ret = lib_func(obj, opt_as_char, val_as_char, len(value))
    pynng.check_err(ret)


def _getopt_bool(py_obj, option):
    """Return the boolean value of the specified option"""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    b = _ffi.new("bool []", 1)
    obj, lib_func = _get_inst_and_func(py_obj, "bool", "get")
    ret = lib_func(obj, opt_as_char, b)
    pynng.check_err(ret)
    return b[0]


def _setopt_bool(py_obj, option, value):
    """Sets the specified option to the specified value."""
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "bool", "set")
    ret = lib_func(obj, opt_as_char, value)
    pynng.check_err(ret)


def _getopt_sockaddr(py_obj, option):
    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    opt_as_char = to_char(option, ffi=_ffi)
    sock_addr = _ffi.new("nng_sockaddr []", 1)
    obj, lib_func = _get_inst_and_func(py_obj, "addr", "get")
    ret = lib_func(obj, opt_as_char, sock_addr)
    pynng.check_err(ret)
    return pynng.sockaddr._nng_sockaddr(sock_addr)


def _setopt_ptr(py_obj, option, value):
    if isinstance(value, pynng.tls.TLSConfig):
        value_ptr = value._tls_config
    else:
        msg = "Invalid value {} of type {}.  Expected TLSConfig."
        msg = msg.format(value, type(value))
        raise ValueError(msg)

    _lib, _ffi = _resolve_lib_ffi(py_obj)
    from ._base import to_char
    option_char = to_char(option, ffi=_ffi)
    obj, lib_func = _get_inst_and_func(py_obj, "ptr", "set")
    ret = lib_func(obj, option_char, value_ptr)
    pynng.check_err(ret)
