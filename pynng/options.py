import pynng
import pynng.sockaddr


def _get_inst_and_func(wrapper_object, option_type, get_or_set):
    """
    Given the Python wrapper for one of nng's object types, return a tuple of
    (nng_object, nng_function).

    Args:
        wrapper_object Union(pynng.Socket, pynng.Dialer, pynng.Listener): the Python wrapper of
          the library type.
        option_type (str): The type of option.

    Returns:
        The tuple (nng_object, nng_func) for use in the module-level getopt*,
            setopt* functions

    """
    # map Python wrapper class to nng attribute
    nng_type_map = {
        pynng.Socket: 'socket',
        pynng.Dialer: 'dialer',
        pynng.Listener: 'listener'
    }

    option_to_func_map = {
        'int': 'nng_getopt_int',
        'size': 'nng_getopt_size',
        'ms': 'nng_getopt_ms',
        'string': 'nng_getopt_string',
        'bool': 'nng_getopt_bool',
        'sockaddr': 'nng_getopt_sockaddr',
    }

    t = type(wrapper_object)
    type_ok = True
    if issubclass(t, pynng.Socket):
        base_type = pynng.Socket
    elif issubclass(t, pynng.Dialer):
        base_type = pynng.Dialer
    elif issubclass(t, pynng.Listener):
        base_type = pynng.Listener
    option_ok = option_type in option_to_func_map
    get_ok = get_or_set in ('get', 'set')
    assert type_ok, 'The type {} is not supported'.format(t)
    assert option_ok, 'The option "{}" is not supported'.format(option_type)
    assert get_ok, 'get_or_set of "{}" is not supported'.format(get_or_set)

    obj = getattr(wrapper_object, nng_type_map[base_type])
    basic_funcname = option_to_func_map[option_type]
    if base_type is pynng.Socket:
        funcname = basic_funcname
    elif base_type is pynng.Dialer:
        funcname = basic_funcname.replace('nng_', 'nng_dialer_')
    elif base_type is pynng.Listener:
        funcname = basic_funcname.replace('nng_', 'nng_listener_')
    else:
        assert False

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


