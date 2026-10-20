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
    """Test that _nng_sockaddr correctly dispatches NNG_AF_ABSTRACT to AbstractAddr.

    NOTE: Uses Python mock objects to simulate CFFI structs.
    This tests the Python-side dispatch logic but cannot catch issues
    with actual CFFI memory access patterns. See Linux-specific tests
    for real CFFI integration coverage.
    """
    from pynng.sockaddr import _nng_sockaddr

    # Create a mock sockaddr with abstract family to verify dispatch
    class MockAbstractSockAddr:
        def __init__(self):
            self.s_family = pynng.lib.NNG_AF_ABSTRACT
            self.s_abstract = MockAbstract()

    class MockAbstract:
        def __init__(self):
            self.sa_len = 4
            self.sa_name = bytearray(107)
            self.sa_name[0:4] = b"test"

    mock_addr = [MockAbstractSockAddr()]
    result = _nng_sockaddr(mock_addr)
    assert isinstance(result, pynng.sockaddr.AbstractAddr)
    assert result.family == pynng.lib.NNG_AF_ABSTRACT


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
    """Test AbstractAddr name_bytes property.

    NOTE: Uses Python mock objects to simulate CFFI structs.
    This tests the Python-side dispatch logic but cannot catch issues
    with actual CFFI memory access patterns. See Linux-specific tests
    for real CFFI integration coverage.
    """

    # Create a mock abstract sockaddr
    class MockAbstractSockAddr:
        def __init__(self):
            self.s_family = pynng.lib.NNG_AF_ABSTRACT
            self.s_abstract = MockAbstract()

    class MockAbstract:
        def __init__(self):
            self.sa_len = 5
            self.sa_name = bytearray(107)
            # Set first 5 bytes
            self.sa_name[0:5] = [ord("t"), ord("e"), ord("s"), ord("t"), 0]

    # Create a mock ffi_sock_addr
    mock_sock_addr = [MockAbstractSockAddr()]

    # Create AbstractAddr instance
    abstract_addr = pynng.sockaddr.AbstractAddr(mock_sock_addr)

    # Test name_bytes property
    name_bytes = abstract_addr.name_bytes
    assert len(name_bytes) == 5
    assert name_bytes == b"test\x00"


def test_abstract_addr_name_with_null_bytes():
    """Test AbstractAddr name property with embedded NUL bytes in raw name data.

    NOTE: Uses Python mock objects to simulate CFFI structs.
    This tests the Python-side dispatch logic but cannot catch issues
    with actual CFFI memory access patterns. See Linux-specific tests
    for real CFFI integration coverage.
    """

    class MockAbstractSockAddr:
        def __init__(self):
            self.s_family = pynng.lib.NNG_AF_ABSTRACT
            self.s_abstract = MockAbstract()

    class MockAbstract:
        def __init__(self):
            self.sa_len = 11
            self.sa_name = bytearray(107)
            test_bytes = b"test\x00socket"
            self.sa_name[0:11] = test_bytes

    mock_sock_addr = [MockAbstractSockAddr()]
    abstract_addr = pynng.sockaddr.AbstractAddr(mock_sock_addr)

    # Verify the exact decoded name, including the NUL byte
    name = abstract_addr.name
    assert name == "test\x00socket"


def test_abstract_addr_str_representation():
    """Test AbstractAddr string representation.

    NOTE: Uses Python mock objects to simulate CFFI structs.
    This tests the Python-side dispatch logic but cannot catch issues
    with actual CFFI memory access patterns. See Linux-specific tests
    for real CFFI integration coverage.
    """

    class MockAbstractSockAddr:
        def __init__(self):
            self.s_family = pynng.lib.NNG_AF_ABSTRACT
            self.s_abstract = MockAbstract()

    class MockAbstract:
        def __init__(self):
            self.sa_len = 9
            self.sa_name = bytearray(107)
            test_bytes = b"test_name"
            self.sa_name[0:9] = test_bytes

    mock_sock_addr = [MockAbstractSockAddr()]
    abstract_addr = pynng.sockaddr.AbstractAddr(mock_sock_addr)

    # Verify exact string representation
    addr_str = str(abstract_addr)
    assert addr_str == "abstract://test_name"
