import pynng
import pynng.sockaddr
import pynng.tls


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

    # map Python wrapper class to nng attribute
    option_to_func_map = {
        'int': 'nng_getopt_int',
        'size': 'nng_getopt_size',
        'ms': 'nng_getopt_ms',
        'string': 'nng_getopt_string',
        'bool': 'nng_getopt_bool',
        'sockaddr': 'nng_getopt_sockaddr',
        'ptr': 'nng_getopt_ptr',
    }

    if option_type not in option_to_func_map:
        raise ValueError('Bad option type "{}"'.format(option_type))

    basic_funcname = option_to_func_map[option_type]
    if isinstance(py_obj, pynng.Socket):
        funcname = basic_funcname
        obj = py_obj.socket
    elif isinstance(py_obj, pynng.Dialer):
        funcname = basic_funcname.replace('nng_', 'nng_dialer_')
        obj = py_obj.dialer
    elif isinstance(py_obj, pynng.Listener):
        funcname = basic_funcname.replace('nng_', 'nng_listener_')
        obj = py_obj.listener
    elif isinstance(py_obj, pynng.Pipe):
        funcname = basic_funcname.replace('nng_', 'nng_pipe_')
        obj = py_obj.pipe
    else:
        msg = 'The type "{}" is not supported'
        msg = msg.format(type(py_obj))
        raise TypeError(msg)

    if get_or_set == 'set':
        funcname = funcname.replace('getopt', 'setopt')
        # special-case for nng_setopt_string, which expects NULL-terminated
        # strings; we use the generic setopt in that case.
        if option_type == 'string':
            funcname = funcname.replace('_string', '')

    nng_func = getattr(pynng.lib, funcname)
    return obj, nng_func


def _getopt_int(obj, option):
    """Gets the specified option"""
    i = pynng.ffi.new('int []', 1)
    opt_as_char = pynng.nng.to_char(option)
    obj, lib_func = _get_inst_and_func(obj, 'int', 'get')
    # attempt to accept floats that are exactly int
    ret = lib_func(obj, opt_as_char, i)
    pynng.check_err(ret)
    return i[0]


def _setopt_int(py_obj, option, value):
    """Sets the specified option to the specified value"""
    opt_as_char = pynng.nng.to_char(option)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    obj, lib_func = _get_inst_and_func(py_obj, 'int', 'set')
    value = int(value)
    err = lib_func(obj, opt_as_char, value)
    pynng.check_err(err)


def _getopt_size(py_obj, option):
    """Gets the specified size option"""
    i = pynng.ffi.new('size_t []', 1)
    opt_as_char = pynng.nng.to_char(option)
    # attempt to accept floats that are exactly int
    obj, lib_func = _get_inst_and_func(py_obj, 'size', 'get')
    ret = lib_func(obj, opt_as_char, i)
    pynng.check_err(ret)
    return i[0]


def _setopt_size(py_obj, option, value):
    """Sets the specified size option to the specified value"""
    opt_as_char = pynng.nng.to_char(option)
    # attempt to accept floats that are exactly int
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'size', 'set')
    lib_func(obj, opt_as_char, value)


def _getopt_ms(py_obj, option):
    """Gets the specified option"""
    ms = pynng.ffi.new('nng_duration []', 1)
    opt_as_char = pynng.nng.to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'ms', 'get')
    ret = lib_func(obj, opt_as_char, ms)
    pynng.check_err(ret)
    return ms[0]


def _setopt_ms(py_obj, option, value):
    """Sets the specified option to the specified value"""
    opt_as_char = pynng.nng.to_char(option)
    # attempt to accept floats that are exactly int (duration types are
    # just integers)
    if not int(value) == value:
        msg = 'Invalid value {} of type {}.  Expected int.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)
    value = int(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'ms', 'set')
    lib_func(obj, opt_as_char, value)


def _getopt_string(py_obj, option):
    """Gets the specified string option"""
    opt = pynng.ffi.new('char *[]', 1)
    opt_as_char = pynng.nng.to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'string', 'get')
    ret = lib_func(obj, opt_as_char, opt)
    pynng.check_err(ret)
    py_string = pynng.ffi.string(opt[0]).decode()
    pynng.lib.nng_strfree(opt[0])
    return py_string


def _setopt_string(py_obj, option, value):
    """Sets the specified option to the specified value

    This is different than the library's nng_setopt_string, because it
    expects the string to be NULL terminated, and we don't.
    """
    opt_as_char = pynng.nng.to_char(option)
    val_as_char = pynng.nng.to_char(value)
    obj, lib_func = _get_inst_and_func(py_obj, 'string', 'set')
    ret = lib_func(obj, opt_as_char, val_as_char, len(value))
    pynng.check_err(ret)


def _getopt_bool(py_obj, option):
    """Return the boolean value of the specified option"""
    opt_as_char = pynng.nng.to_char(option)
    b = pynng.ffi.new('bool []', 1)
    obj, lib_func = _get_inst_and_func(py_obj, 'bool', 'get')
    ret = lib_func(obj, opt_as_char, b)
    pynng.check_err(ret)
    return b[0]


def _setopt_bool(py_obj, option, value):
    """Sets the specified option to the specified value."""
    opt_as_char = pynng.nng.to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'bool', 'set')
    ret = lib_func(obj, opt_as_char, value)
    pynng.check_err(ret)


def _getopt_sockaddr(py_obj, option):
    opt_as_char = pynng.nng.to_char(option)
    sock_addr = pynng.ffi.new('nng_sockaddr []', 1)
    obj, lib_func = _get_inst_and_func(py_obj, 'sockaddr', 'get')
    ret = lib_func(obj, opt_as_char, sock_addr)
    pynng.check_err(ret)
    return pynng.sockaddr._nng_sockaddr(sock_addr)


def _setopt_ptr(py_obj, option, value):
    if isinstance(value, pynng.tls.TLSConfig):
        value_ptr = value._tls_config
    else:
        msg = 'Invalid value {} of type {}.  Expected TLSConfig.'
        msg = msg.format(value, type(value))
        raise ValueError(msg)

    option_char = pynng.nng.to_char(option)
    obj, lib_func = _get_inst_and_func(py_obj, 'ptr', 'set')
    ret = lib_func(obj, option_char, value_ptr)
    pynng.check_err(ret)
