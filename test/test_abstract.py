import pytest
import pynng
import pynng.sockaddr
import platform

from _test_util import wait_pipe_len
from conftest import FAST_TIMEOUT


def test_abstract_addr_basic():
    """Test basic AbstractAddr functionality"""
    # Test that NNG_AF_ABSTRACT is available
    assert hasattr(pynng.lib, "NNG_AF_ABSTRACT")
    assert pynng.lib.NNG_AF_ABSTRACT == 6
    # Verify the Python AbstractAddr class exists and is a proper SockAddr subclass
    assert hasattr(pynng.sockaddr, "AbstractAddr")
    assert issubclass(pynng.sockaddr.AbstractAddr, pynng.sockaddr.SockAddr)


def test_abstract_addr_in_type_to_str():
    """Test that abstract socket family is in type_to_str mapping"""
    assert pynng.lib.NNG_AF_ABSTRACT in pynng.sockaddr.SockAddr.type_to_str
    assert pynng.sockaddr.SockAddr.type_to_str[pynng.lib.NNG_AF_ABSTRACT] == "abstract"


def test_nng_sockaddr_dispatch_includes_abstract():
    """Test that _nng_sockaddr correctly dispatches NNG_AF_ABSTRACT to AbstractAddr."""
    from pynng.sockaddr import _nng_sockaddr

    c_addr = pynng.ffi.new("nng_sockaddr *")
    c_addr.s_family = pynng.lib.NNG_AF_ABSTRACT
    c_addr.s_abstract.sa_len = 4
    c_addr.s_abstract.sa_name[0:4] = b"test"

    result = _nng_sockaddr(c_addr)
    assert isinstance(result, pynng.sockaddr.AbstractAddr)
    assert result.family == pynng.lib.NNG_AF_ABSTRACT
    assert result.family_as_str == "abstract"
    assert result.name_bytes == b"test"
    assert result.name == "test"
    assert str(result) == "abstract://test"


@pytest.mark.skipif(
    platform.system() != "Linux", reason="Abstract sockets are Linux-specific"
)
def test_abstract_socket_connection():
    """Test actual abstract socket connection on Linux"""
    # Test with a simple abstract socket name
    abstract_addr = "abstract://test_socket"

    with pynng.Pair0(recv_timeout=FAST_TIMEOUT) as sock1, pynng.Pair0(
        recv_timeout=FAST_TIMEOUT
    ) as sock2:
        # Test listening on abstract socket
        listener = sock1.listen(abstract_addr)
        assert len(sock1.listeners) == 1

        # Test dialing abstract socket
        sock2.dial(abstract_addr)
        assert len(sock2.dialers) == 1
        wait_pipe_len(sock1, 1)

        # Test basic communication
        sock1.send(b"hello")
        received = sock2.recv()
        assert received == b"hello"

        # Test that local address is AbstractAddr
        local_addr = listener.local_address
        assert isinstance(local_addr, pynng.sockaddr.AbstractAddr)
        assert local_addr.family == pynng.lib.NNG_AF_ABSTRACT
        assert local_addr.family_as_str == "abstract"


@pytest.mark.skipif(
    platform.system() != "Linux", reason="Abstract sockets are Linux-specific"
)
def test_abstract_socket_with_special_chars():
    """Test abstract socket with special characters including NUL bytes"""
    # Test with URI-encoded special characters
    abstract_addr = "abstract://test%00socket%20with%20spaces"

    with pynng.Pair0(recv_timeout=FAST_TIMEOUT) as sock1, pynng.Pair0(recv_timeout=FAST_TIMEOUT) as sock2:
        listener = sock1.listen(abstract_addr)
        sock2.dial(abstract_addr)
        wait_pipe_len(sock1, 1)

        # Test communication
        sock1.send(b"test message")
        received = sock2.recv()
        assert received == b"test message"

        # Test that the address is properly handled
        local_addr = listener.local_address
        assert isinstance(local_addr, pynng.sockaddr.AbstractAddr)

        # Test string representation
        addr_str = str(local_addr)
        assert addr_str.startswith("abstract://")


@pytest.mark.skipif(
    platform.system() != "Linux", reason="Abstract sockets are Linux-specific"
)
def test_abstract_socket_auto_bind():
    """Test that abstract sockets can auto-bind (assign a random name).

    Note: Even if auto-bind works, there is no API to retrieve the
    assigned name, so we cannot dial it. This test only verifies that
    listen() on an empty abstract address does not crash.
    """
    # Test with empty abstract socket name for auto-bind
    abstract_addr = "abstract://"

    with pynng.Pair0(listen=abstract_addr, recv_timeout=FAST_TIMEOUT) as sock1:
        # If auto-bind works, the socket should have a listener with an address
        assert len(sock1.listeners) > 0, "Auto-bind should create a listener"


@pytest.mark.skipif(
    platform.system() != "Linux", reason="Abstract sockets are Linux-specific"
)
def test_abstract_socket_with_different_protocols():
    """Test abstract sockets with different protocol types"""
    protocols = [
        (pynng.Pair0, pynng.Pair0, "pair"),
        (pynng.Pub0, pynng.Sub0, "pubsub"),
        (pynng.Push0, pynng.Pull0, "pushpull"),
        (pynng.Req0, pynng.Rep0, "reqrep"),
    ]

    for server_proto, client_proto, proto_name in protocols:
        abstract_addr = f"abstract://test_{proto_name}_protocol"

        with server_proto(recv_timeout=FAST_TIMEOUT) as server, client_proto(
            recv_timeout=FAST_TIMEOUT
        ) as client:
            if server_proto == pynng.Pub0 and client_proto == pynng.Sub0:
                # pub/sub: subscriber must subscribe before receiving
                server.listen(abstract_addr)
                client.dial(abstract_addr)
                client.subscribe("")  # Subscribe to all messages
                wait_pipe_len(server, 1)
                server.send(b"pubsub test")
                received = client.recv()
                assert received == b"pubsub test", f"Failed for protocol: {proto_name}"
            elif server_proto == pynng.Push0 and client_proto == pynng.Pull0:
                # push/pull: unidirectional from push to pull
                server.listen(abstract_addr)
                client.dial(abstract_addr)
                wait_pipe_len(server, 1)
                server.send(b"pushpull test")
                received = client.recv()
                assert received == b"pushpull test", f"Failed for protocol: {proto_name}"
            elif server_proto == pynng.Req0 and client_proto == pynng.Rep0:
                # req/rep: rep listens, req dials; req sends then rep replies
                client.listen(abstract_addr)
                server.dial(abstract_addr)
                wait_pipe_len(client, 1)
                server.send(b"reqrep test")
                received = client.recv()
                assert received == b"reqrep test", f"Failed recv for protocol: {proto_name}"
                client.send(b"reply")
                reply = server.recv()
                assert reply == b"reply", f"Failed reply for protocol: {proto_name}"
            else:
                # pair: bidirectional, either side can send first
                server.listen(abstract_addr)
                client.dial(abstract_addr)
                wait_pipe_len(server, 1)
                server.send(b"pair test")
                received = client.recv()
                assert received == b"pair test", f"Failed for protocol: {proto_name}"


@pytest.mark.skipif(
    platform.system() == "Linux", reason="Test error handling on non-Linux systems"
)
def test_abstract_socket_error_on_non_linux():
    """Test that abstract sockets raise appropriate errors on non-Linux systems"""
    abstract_addr = "abstract://test_socket"

    with pynng.Pair0() as sock:
        with pytest.raises(pynng.exceptions.NNGException):
            sock.listen(abstract_addr)


def test_abstract_addr_name_bytes():
    """Test AbstractAddr name_bytes property with real CFFI nng_sockaddr."""
    c_addr = pynng.ffi.new("nng_sockaddr *")
    c_addr.s_family = pynng.lib.NNG_AF_ABSTRACT
    c_addr.s_abstract.sa_len = 5
    c_addr.s_abstract.sa_name[0:5] = b"test\x00"

    abstract_addr = pynng.sockaddr.AbstractAddr(c_addr)
    name_bytes = abstract_addr.name_bytes
    assert len(name_bytes) == 5
    assert name_bytes == b"test\x00"


def test_abstract_addr_name_with_null_bytes():
    """Test AbstractAddr name property with embedded NUL and literal percent bytes."""
    c_addr = pynng.ffi.new("nng_sockaddr *")
    c_addr.s_family = pynng.lib.NNG_AF_ABSTRACT
    test_bytes = b"test\x00%41socket"
    c_addr.s_abstract.sa_len = len(test_bytes)
    c_addr.s_abstract.sa_name[0 : len(test_bytes)] = test_bytes

    abstract_addr = pynng.sockaddr.AbstractAddr(c_addr)
    assert abstract_addr.name == "test\x00%41socket"
    assert str(abstract_addr) == "abstract://test%00%2541socket"


def test_abstract_addr_non_utf8():
    """Test AbstractAddr name and str properties with non-UTF-8 raw bytes."""
    c_addr = pynng.ffi.new("nng_sockaddr *")
    c_addr.s_family = pynng.lib.NNG_AF_ABSTRACT
    raw = b"\xff\xfe\x00ab"
    c_addr.s_abstract.sa_len = len(raw)
    c_addr.s_abstract.sa_name[0 : len(raw)] = raw

    abstract_addr = pynng.sockaddr.AbstractAddr(c_addr)
    assert abstract_addr.name_bytes == raw
    assert abstract_addr.name.encode("utf-8", errors="surrogateescape") == raw
    assert str(abstract_addr) == "abstract://%FF%FE%00ab"


def test_abstract_addr_str_representation():
    """Test AbstractAddr string representation."""
    c_addr = pynng.ffi.new("nng_sockaddr *")
    c_addr.s_family = pynng.lib.NNG_AF_ABSTRACT
    test_bytes = b"test_name"
    c_addr.s_abstract.sa_len = len(test_bytes)
    c_addr.s_abstract.sa_name[0 : len(test_bytes)] = test_bytes

    abstract_addr = pynng.sockaddr.AbstractAddr(c_addr)
    assert str(abstract_addr) == "abstract://test_name"
