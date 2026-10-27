import threading

import pynng

from ._finalized import (
    is_nng_finalized as _is_nng_finalized,
    retain_closed as _retain_closed,
)


# Every initialized nng library (v1 always; v2 once pynng.v2 is imported).
# A TLSConfig allocates one nng_tls_config per library at construction, so
# its setters reach every library at once and it never has to keep the
# arguments (private keys, passwords) for a later replay.
_libs = [(pynng.lib, pynng.ffi)]
_libs_lock = threading.Lock()

_MODE_NAMES = ("NNG_TLS_MODE_CLIENT", "NNG_TLS_MODE_SERVER")
_AUTH_MODE_NAMES = (
    "NNG_TLS_AUTH_MODE_NONE",
    "NNG_TLS_AUTH_MODE_OPTIONAL",
    "NNG_TLS_AUTH_MODE_REQUIRED",
)


def _register_lib(lib, ffi):
    """Make TLSConfig objects created from now on also allocate for ``lib``."""
    with _libs_lock:
        if all(known is not lib for known, _ in _libs):
            _libs.append((lib, ffi))


def _translate_constant(value, names, src_lib, dst_lib):
    for name in names:
        if getattr(src_lib, name) == value:
            return getattr(dst_lib, name)
    raise ValueError(f"Unknown TLS constant {value!r}")


class _Unavailable:
    """Why a TLSConfig has no usable nng_tls_config for one nng library."""

    __slots__ = ("diverged_cfg", "error")

    def __init__(self, error, diverged_cfg=None):
        self.error = error
        # (ffi, nng_tls_config *) still owned by the TLSConfig, or None.
        self.diverged_cfg = diverged_cfg


class TLSConfig:
    """
    TLS Configuration object.  This object is used to configure sockets that
    are using the TLS transport.

    Args:
        mode: Must be ``TLSConfig.MODE_CLIENT`` or ``TLSConfig.MODE_SERVER``.
            Corresponds to nng's ``mode`` argument in ``nng_tls_config_alloc``.
        server_name (str): When configuring a client, ``server_name`` is used
            to compare the identity of the server's certificate.  Corresponds
            to ``nng_tls_config_server_name``.
        ca_string (str):  Set certificate authority with a string.  Corresponds
            to ``nng_tls_config_ca_chain``
        own_key_string (str):  When passed with ``own_cert_string``, is used to
            set own certificate.  Corresponds to ``nng_tls_config_own_cert``.
        own_cert_string (str): When passed with ``own_key_string``, is used to
            set own certificate.  Corresponds to ``nng_tls_config_own_cert``.
        auth_mode: Set the authentication mode of the connection.  Corresponds
            to ``nng_tls_config_auth_mode``.
        ca_files (str or list[str]): ca files to use for the TLS connection.
            Corresponds to ``nng_tls_config_ca_file``.
        cert_key_file (str):  Corresponds to ``nng_tls_config_cert_key_file``.
        passwd (str):  Password used for configuring certificates.

    Check the `TLS tests
    <https://github.com/codypiersall/pynng/blob/master/test/test_tls.py>`_ for
    usage examples.

    """

    MODE_CLIENT = pynng.lib.NNG_TLS_MODE_CLIENT
    MODE_SERVER = pynng.lib.NNG_TLS_MODE_SERVER

    AUTH_MODE_NONE = pynng.lib.NNG_TLS_AUTH_MODE_NONE
    AUTH_MODE_OPTIONAL = pynng.lib.NNG_TLS_AUTH_MODE_OPTIONAL
    AUTH_MODE_REQUIRED = pynng.lib.NNG_TLS_AUTH_MODE_REQUIRED

    _lib = pynng.lib
    _ffi = pynng.ffi

    def __init__(
        self,
        mode,
        server_name=None,
        ca_string=None,
        own_key_string=None,
        own_cert_string=None,
        auth_mode=None,
        ca_files=None,
        cert_key_file=None,
        passwd=None,
    ):
        self._tls_config = None
        # lib -> (ffi, nng_tls_config *) for every other initialized library,
        # or lib -> _Unavailable when that library cannot use this config.
        self._alt_configs = {}
        if ca_string and ca_files:
            raise ValueError("Cannot set both ca_string and ca_files!")

        if (own_cert_string or own_key_string) and cert_key_file:
            raise ValueError("Cannot set both own_{key,cert}_string and cert_key_file!")

        if bool(own_cert_string) != bool(own_key_string):
            raise ValueError(
                "own_key_string and own_cert_string must be both set or unset"
            )

        if isinstance(ca_files, str):
            # assume the user really intended to only set a single ca file.
            ca_files = [ca_files]

        tls_config_p = self._ffi.new("nng_tls_config **")
        pynng.check_err(
            self._lib.nng_tls_config_alloc(tls_config_p, mode),
            lib=self._lib,
            ffi=self._ffi,
        )
        self._tls_config = tls_config_p[0]
        _retain_closed(self)

        with _libs_lock:
            other_libs = [(lb, ff) for lb, ff in _libs if lb is not self._lib]
        for alt_lib, alt_ffi in other_libs:
            alt_mode = _translate_constant(mode, _MODE_NAMES, self._lib, alt_lib)
            alt_p = alt_ffi.new("nng_tls_config **")
            err = alt_lib.nng_tls_config_alloc(alt_p, alt_mode)
            if err == alt_lib.NNG_ENOTSUP:
                # That library was built without TLS; using this config with
                # it raises, using it with the others works.
                try:
                    pynng.check_err(err, lib=alt_lib, ffi=alt_ffi)
                except pynng.NotSupported as exc:
                    self._alt_configs[alt_lib] = _Unavailable(exc)
                continue
            pynng.check_err(err, lib=alt_lib, ffi=alt_ffi)
            self._alt_configs[alt_lib] = (alt_ffi, alt_p[0])

        if server_name is not None:
            self.set_server_name(server_name)

        if ca_string:
            self.set_ca_chain(ca_string)

        if own_key_string and own_cert_string:
            self.set_own_cert(own_cert_string, own_key_string, passwd)

        if auth_mode is not None:
            self.set_auth_mode(auth_mode)

        if ca_files:
            for f in ca_files:
                self.add_ca_file(f)

        if cert_key_file:
            self.set_cert_key_file(cert_key_file, passwd)

    @staticmethod
    def _apply_op(lib, ffi, cfg, op_name, args):
        to_char = pynng.nng.to_char
        if op_name == "server_name":
            (server_name,) = args
            err = lib.nng_tls_config_server_name(cfg, to_char(server_name, ffi=ffi))
            pynng.check_err(err, lib=lib, ffi=ffi)
        elif op_name == "ca_chain":
            chain, crl = args
            chain_char = to_char(chain, ffi=ffi)
            crl_char = to_char(crl, ffi=ffi) if crl is not None else ffi.NULL
            err = lib.nng_tls_config_ca_chain(cfg, chain_char, crl_char)
            pynng.check_err(err, lib=lib, ffi=ffi)
        elif op_name == "own_cert":
            cert, key, passwd = args
            cert_char = to_char(cert, ffi=ffi)
            key_char = to_char(key, ffi=ffi)
            passwd_char = to_char(passwd, ffi=ffi) if passwd is not None else ffi.NULL
            err = lib.nng_tls_config_own_cert(cfg, cert_char, key_char, passwd_char)
            pynng.check_err(err, lib=lib, ffi=ffi)
        elif op_name == "auth_mode":
            (mode,) = args
            err = lib.nng_tls_config_auth_mode(cfg, mode)
            pynng.check_err(err, lib=lib, ffi=ffi)
        elif op_name == "ca_file":
            (path,) = args
            path_char = to_char(path, ffi=ffi)
            err = lib.nng_tls_config_ca_file(cfg, path_char)
            pynng.check_err(err, lib=lib, ffi=ffi)
        elif op_name == "cert_key_file":
            path, passwd = args
            path_char = to_char(path, ffi=ffi)
            passwd_char = to_char(passwd, ffi=ffi) if passwd is not None else ffi.NULL
            err = lib.nng_tls_config_cert_key_file(cfg, path_char, passwd_char)
            pynng.check_err(err, lib=lib, ffi=ffi)

    def _apply_everywhere(self, op_name, args):
        self._apply_op(self._lib, self._ffi, self._tls_config, op_name, args)
        for alt_lib, entry in list(self._alt_configs.items()):
            if isinstance(entry, _Unavailable):
                continue
            alt_ffi, alt_cfg = entry
            alt_args = args
            if op_name == "auth_mode":
                alt_args = (
                    _translate_constant(args[0], _AUTH_MODE_NAMES, self._lib, alt_lib),
                )
            try:
                self._apply_op(alt_lib, alt_ffi, alt_cfg, op_name, alt_args)
            except BaseException as exc:
                # nng has changed the other configs and cannot undo it, so this
                # one no longer has the same settings: refuse to use it again.
                # It stays referenced so that __del__ frees it.
                self._alt_configs[alt_lib] = _Unavailable(
                    RuntimeError(
                        f"TLSConfig.set_{op_name} failed for one nng version "
                        f"after it succeeded for another ({exc!r}), so this "
                        "TLSConfig has different settings for each version "
                        "and cannot be used with that version any more"
                    ),
                    diverged_cfg=(alt_ffi, alt_cfg),
                )
                raise

    def _config_for(self, target_lib=None, target_ffi=None):
        """Return the ``nng_tls_config *`` for ``target_lib``."""
        if target_lib is None or target_lib is self._lib:
            return self._tls_config
        entry = self._alt_configs.get(target_lib)
        if entry is None:
            raise RuntimeError(
                "This TLSConfig was created before that nng version was "
                "initialized, so it has no configuration for it. Import "
                "pynng.v2 before you create a TLSConfig that v2 endpoints use, "
                "or create a pynng.v2.TLSConfig."
            )
        if isinstance(entry, _Unavailable):
            raise entry.error
        return entry[1]

    def __del__(self):
        try:
            if _is_nng_finalized():
                self._tls_config = None
                if hasattr(self, "_alt_configs"):
                    self._alt_configs.clear()
                return
            cfg = getattr(self, "_tls_config", None)
            if cfg is not None and cfg != self._ffi.NULL:
                self._tls_config = None
                self._lib.nng_tls_config_free(cfg)
            alt_configs = getattr(self, "_alt_configs", None)
            if alt_configs:
                for alt_lib, entry in list(alt_configs.items()):
                    if isinstance(entry, _Unavailable):
                        entry = entry.diverged_cfg
                        if entry is None:
                            continue
                    alt_ffi, alt_cfg = entry
                    if alt_cfg is not None and alt_cfg != alt_ffi.NULL:
                        alt_lib.nng_tls_config_free(alt_cfg)
                alt_configs.clear()
        except (TypeError, AttributeError, ImportError):
            # During interpreter shutdown, globals (pynng, lib) may be None
            pass

    def set_server_name(self, server_name):
        """
        Configure remote server name.
        """
        if server_name is None:
            raise ValueError(
                "server_name cannot be None; pass an empty string to clear"
            )
        self._apply_everywhere("server_name", (server_name,))

    def set_ca_chain(self, chain, crl=None):
        """
        Configure certificate authority certificate chain.
        """
        self._apply_everywhere("ca_chain", (chain, crl))

    def set_own_cert(self, cert, key, passwd=None):
        """
        Configure own certificate and key.
        """
        self._apply_everywhere("own_cert", (cert, key, passwd))

    def set_auth_mode(self, mode):
        """
        Configure authentication mode.
        """
        self._apply_everywhere("auth_mode", (mode,))

    def add_ca_file(self, path):
        """
        Add a certificate authority from a file.
        """
        self._apply_everywhere("ca_file", (path,))

    def set_cert_key_file(self, path, passwd=None):
        """
        Load own certificate and key from file.
        """
        self._apply_everywhere("cert_key_file", (path, passwd))
