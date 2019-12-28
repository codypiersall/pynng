import pynng


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
    <https://github.com/codypiersall/pynng/blob/master/test/test_api.py>`_ for
    usage examples.

    """

    MODE_CLIENT = pynng.lib.NNG_TLS_MODE_CLIENT
    MODE_SERVER = pynng.lib.NNG_TLS_MODE_SERVER

    AUTH_MODE_NONE = pynng.lib.NNG_TLS_AUTH_MODE_NONE
    AUTH_MODE_OPTIONAL = pynng.lib.NNG_TLS_AUTH_MODE_OPTIONAL
    AUTH_MODE_REQUIRED = pynng.lib.NNG_TLS_AUTH_MODE_REQUIRED

    def __init__(self, mode,
                 server_name=None,
                 ca_string=None,
                 own_key_string=None,
                 own_cert_string=None,
                 auth_mode=None,
                 ca_files=None,
                 cert_key_file=None,
                 passwd=None):

        if ca_string and ca_files:
            raise ValueError("Cannot set both ca_string and ca_files!")

        if (own_cert_string or own_key_string) and cert_key_file:
            raise ValueError("Cannot set both own_{key,cert}_string an cert_key_file!")

        if bool(own_cert_string) != bool(own_key_string):
            raise ValueError("own_key_string and own_cert_string must be both set or unset")

        if isinstance(ca_files, str):
            # assume the user really intended to only set a single ca file.
            ca_files = [ca_files]

        tls_config_p = pynng.ffi.new('nng_tls_config **')
        pynng.check_err(pynng.lib.nng_tls_config_alloc(tls_config_p, mode))
        self._tls_config = tls_config_p[0]

        if server_name:
            self.set_server_name(server_name)

        if ca_string:
            self.set_ca_chain(ca_string)

        if own_key_string and own_cert_string:
            self.set_own_cert(own_cert_string, own_key_string, passwd)

        if auth_mode:
            self.set_auth_mode(auth_mode)

        if ca_files:
            for f in ca_files:
                self.add_ca_file(f)

        if cert_key_file:
            self.set_cert_key_file(cert_key_file, passwd)

    def __del__(self):
        pynng.lib.nng_tls_config_free(self._tls_config)

    def set_server_name(self, server_name):
        """
        Configure remote server name.
        """
        server_name_char = pynng.nng.to_char(server_name)
        err = pynng.lib.nng_tls_config_server_name(self._tls_config, server_name_char)
        pynng.check_err(err)

    def set_ca_chain(self, chain, crl=None):
        """
        Configure certificate authority certificate chain.
        """
        chain_char = pynng.nng.to_char(chain)
        crl_char = pynng.nng.to_char(crl) if crl is not None else pynng.ffi.NULL

        err = pynng.lib.nng_tls_config_ca_chain(self._tls_config, chain_char, crl_char)
        pynng.check_err(err)

    def set_own_cert(self, cert, key, passwd=None):
        """
        Configure own certificate and key.
        """
        cert_char = pynng.nng.to_char(cert)
        key_char = pynng.nng.to_char(key)
        passwd_char = pynng.nng.to_char(passwd) if passwd is not None else pynng.ffi.NULL

        err = pynng.lib.nng_tls_config_own_cert(self._tls_config, cert_char, key_char, passwd_char)
        pynng.check_err(err)

    def set_auth_mode(self, mode):
        """
        Configure authentication mode.
        """
        err = pynng.lib.nng_tls_config_auth_mode(self._tls_config, mode)
        pynng.check_err(err)

    def add_ca_file(self, path):
        """
        Add a certificate authority from a file.
        """
        path_char = pynng.nng.to_char(path)
        err = pynng.lib.nng_tls_config_ca_file(self._tls_config, path_char)
        pynng.check_err(err)

    def set_cert_key_file(self, path, passwd=None):
        """
        Load own certificate and key from file.
        """
        path_char = pynng.nng.to_char(path)
        passwd_char = pynng.nng.to_char(passwd) if passwd is not None else pynng.ffi.NULL

        err = pynng.lib.nng_tls_config_cert_key_file(self._tls_config, path_char, passwd_char)
        pynng.check_err(err)
