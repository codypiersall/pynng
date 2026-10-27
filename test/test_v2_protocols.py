"""End-to-end communication tests for all 11 NNG v2 socket types."""

import gc
import socket as py_socket
import threading
import time
import pytest

import pynng
from _test_util import wait_pipe_len
from conftest import random_addr, FAST_TIMEOUT, MEDIUM_TIMEOUT

pytestmark = [pytest.mark.nng_v2]

# Ensure pynng.v2 is available before running these tests
v2 = pytest.importorskip("pynng.v2")

from pynng._nng_v2 import ffi as ffi2  # noqa: E402
from pynng._nng_v2 import lib as lib2  # noqa: E402


def _bound_port(listener):
    """The port that nng bound for a started TCP-based v2 listener."""
    port = ffi2.new("int *")
    err = lib2.nng_listener_get_int(listener.listener, b"bound-port", port)
    pynng.check_err(err, lib=lib2, ffi=ffi2)
    return port[0]


def _tls_configs(server_cls, client_cls):
    from test_tls import CA_CERT, SERVER_CERT, SERVER_KEY

    srv_cfg = server_cls(
        server_cls.MODE_SERVER,
        own_key_string=SERVER_KEY,
        own_cert_string=SERVER_CERT,
    )
    cli_cfg = client_cls(
        client_cls.MODE_CLIENT,
        ca_string=CA_CERT,
        server_name="localhost",
    )
    return srv_cfg, cli_cfg


def test_v2_pair0():
    """Verify Pair0 bidirectional communication in v2."""
    addr = random_addr()
    with v2.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        s1.send(b"hello from s1")
        assert s0.recv() == b"hello from s1"
        s0.send(b"reply from s0")
        assert s1.recv() == b"reply from s0"


def test_v2_pair0_dial_listen_instances():
    """Verify s.dial() and s.listen() return v2 Dialer/Listener subclasses."""
    addr = random_addr()
    with v2.Pair0() as s0, v2.Pair0() as s1:
        listener = s0.listen(addr)
        dialer = s1.dial(addr)
        assert isinstance(listener, v2.Listener)
        assert isinstance(dialer, v2.Dialer)


@pytest.mark.asyncio
async def test_v2_pair0_async():
    """Verify Pair0 async arecv/asend in v2."""
    addr = random_addr()
    with v2.Pair0(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        await s1.asend(b"async hello")
        assert await s0.arecv() == b"async hello"


def test_v2_pair1():
    """Verify Pair1 monogamous communication in v2."""
    addr = random_addr()
    with v2.Pair1(listen=addr, recv_timeout=FAST_TIMEOUT) as s0, v2.Pair1(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as s1:
        s1.send(b"pair1 message")
        assert s0.recv() == b"pair1 message"


def test_v2_pair1_polyamorous():
    """Verify Pair1 polyamorous mode with multiple peers in v2."""
    addr = random_addr()
    with v2.Pair1(
        listen=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT
    ) as s0, v2.Pair1(dial=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT) as s1:
        assert s0.polyamorous is True
        assert s1.polyamorous is True
        wait_pipe_len(s0, 1)
        p1 = s0.pipes[0]

        with v2.Pair1(dial=addr, polyamorous=True, recv_timeout=FAST_TIMEOUT) as s2:
            assert s2.polyamorous is True
            wait_pipe_len(s0, 2)
            pipes = s0.pipes
            p2 = pipes[1] if pipes[0] is p1 else pipes[0]

            p1.send(b"msg to s1")
            assert s1.recv() == b"msg to s1"

            p2.send(b"msg to s2")
            assert s2.recv() == b"msg to s2"


def test_v2_req0_rep0():
    """Verify Req0 and Rep0 request-reply lifecycle and state machine in v2."""
    addr = random_addr()
    with v2.Req0(listen=addr, recv_timeout=FAST_TIMEOUT) as req, v2.Rep0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as rep:
        req.send(b"ping")
        assert rep.recv() == b"ping"
        rep.send(b"pong")
        assert req.recv() == b"pong"

        # Req cannot receive before sending
        with pytest.raises(pynng.BadState):
            req.recv()

        # Rep cannot send before receiving
        with pytest.raises(pynng.BadState):
            rep.send(b"unsolicited")


def test_v2_pub0_sub0():
    """Verify Pub0 and Sub0 topic matching in v2."""
    addr = random_addr()
    with v2.Sub0(listen=addr, recv_timeout=FAST_TIMEOUT) as sub, v2.Pub0(
        dial=addr, recv_timeout=FAST_TIMEOUT
    ) as pub:
        sub.subscribe(b"sports:")
        wait_pipe_len(sub, 1)
        wait_pipe_len(pub, 1)

        # Non-matching message is not received
        pub.send(b"weather: rainy")
        with pytest.raises(pynng.Timeout):
            sub.recv()

        # Matching message is received
        pub.send(b"sports: goals scored")
        assert sub.recv() == b"sports: goals scored"

        # Pub cannot recv
        with pytest.raises(pynng.NotSupported):
            pub.recv()

        # Sub cannot send
        with pytest.raises(pynng.NotSupported):
            sub.send(b"cannot send")


def test_v2_sub0_subscriptions_parity():
    """Verify Sub0 subscriptions property tracking parity in v2."""
    with v2.Sub0() as sub:
        assert sub.subscriptions == frozenset()

        sub.subscribe("news:")
        assert sub.subscriptions == frozenset({b"news:"})

        sub.subscribe(b"alerts:")
        assert sub.subscriptions == frozenset({b"news:", b"alerts:"})

        # Duplicates ignored in set
        sub.subscribe("news:")
        assert sub.subscriptions == frozenset({b"news:", b"alerts:"})

        sub.unsubscribe("news:")
        assert sub.subscriptions == frozenset({b"alerts:"})

        sub.subscribe_all(["cat1", b"cat2"])
        assert sub.subscriptions == frozenset({b"alerts:", b"cat1", b"cat2"})

        sub.unsubscribe_all()
        assert sub.subscriptions == frozenset()


def test_v2_sub0_constructor_topics():
    """Verify Sub0 constructor topic subscription in v2."""
    addr = random_addr()
    with v2.Pub0(listen=addr) as pub:
        with v2.Sub0(dial=addr, topics=["alpha", "beta"], recv_timeout=FAST_TIMEOUT) as sub:
            assert sub.subscriptions == frozenset({b"alpha", b"beta"})
            wait_pipe_len(sub, 1)
            wait_pipe_len(pub, 1)
            pub.send(b"alpha 1")
            assert sub.recv() == b"alpha 1"
            pub.send(b"beta 2")
            assert sub.recv() == b"beta 2"


def test_v2_push0_pull0():
    """Verify Push0 and Pull0 distribution in v2."""
    addr = random_addr()
    received = {"pull1": None, "pull2": None}
    with v2.Push0(listen=addr) as push, v2.Pull0(
        dial=addr, recv_timeout=MEDIUM_TIMEOUT
    ) as pull1, v2.Pull0(dial=addr, recv_timeout=MEDIUM_TIMEOUT) as pull2:

        def recv1():
            received["pull1"] = pull1.recv()

        def recv2():
            received["pull2"] = pull2.recv()

        t1 = threading.Thread(target=recv1, daemon=True)
        t2 = threading.Thread(target=recv2, daemon=True)

        t1.start()
        t2.start()
        wait_pipe_len(push, 2)
        wait_pipe_len(pull1, 1)
        wait_pipe_len(pull2, 1)

        push.send(b"item 1")
        push.send(b"item 2")
        t1.join()
        t2.join()

        assert {received["pull1"], received["pull2"]} == {b"item 1", b"item 2"}

        with pytest.raises(pynng.NotSupported):
            push.recv()


def test_v2_surveyor0_respondent0():
    """Verify Surveyor0 and Respondent0 survey lifecycle in v2."""
    addr = random_addr()
    with v2.Surveyor0(listen=addr, recv_timeout=MEDIUM_TIMEOUT) as surveyor, v2.Respondent0(
        dial=addr, recv_timeout=MEDIUM_TIMEOUT
    ) as resp1, v2.Respondent0(dial=addr, recv_timeout=MEDIUM_TIMEOUT) as resp2:
        wait_pipe_len(surveyor, 2)
        surveyor.send(b"survey question")

        assert resp1.recv() == b"survey question"
        resp1.send(b"resp1 answer")

        assert resp2.recv() == b"survey question"
        resp2.send(b"resp2 answer")

        answers = {surveyor.recv(), surveyor.recv()}
        assert answers == {b"resp1 answer", b"resp2 answer"}


def test_v2_bus0():
    """Verify Bus0 mesh broadcast in v2."""
    addr = random_addr()
    with v2.Bus0(recv_timeout=FAST_TIMEOUT) as s0, v2.Bus0(
        recv_timeout=FAST_TIMEOUT
    ) as s1, v2.Bus0(recv_timeout=FAST_TIMEOUT) as s2:
        s0.listen(addr)
        s1.dial(addr)
        s2.dial(addr)
        wait_pipe_len(s0, 2)

        s0.send(b"s1 and s2 get this")
        assert s1.recv() == b"s1 and s2 get this"
        assert s2.recv() == b"s1 and s2 get this"

        s1.send(b"only s0 gets this")
        assert s0.recv() == b"only s0 gets this"
        with pytest.raises(pynng.Timeout):
            s2.recv()


def test_v2_pipe_addresses():
    """Verify local_address and remote_address symmetry on v2 pipes."""
    addr = random_addr()
    with v2.Pair0(listen=addr) as s0, v2.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]

        assert isinstance(p0.local_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p0.remote_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p1.local_address, pynng.sockaddr.InprocAddr)
        assert isinstance(p1.remote_address, pynng.sockaddr.InprocAddr)

        # Symmetry: s0's local is s1's remote, and vice versa
        assert str(p0.local_address) == str(p1.remote_address)
        assert str(p0.remote_address) == str(p1.local_address)


def test_v2_dialer_listener_addresses_graceful():
    """Verify dialer and listener local/remote address access does not raise."""
    addr = random_addr()
    with v2.Pair0() as s0, v2.Pair0() as s1:
        l = s0.listen(addr)
        d = s1.dial(addr)
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)

        # Accessing these properties must not raise AttributeError or crash
        assert l.local_address is not None
        assert l.remote_address is None
        assert d.local_address is not None
        assert d.remote_address is not None


def test_v2_message_memory_safety():
    """Verify v2 Message frees memory on failure and handles __del__ safely."""
    with pytest.raises(Exception):
        v2.Message(None)
    gc.collect()

    # Valid message lifecycle
    msg = v2.Message(b"test data")
    assert msg.bytes == b"test data"
    del msg
    gc.collect()


def test_v2_pipe_scheme():
    """Verify Pipe.scheme returns the transport scheme in v2."""
    addr = random_addr()
    with v2.Pair0(listen=addr) as s0, v2.Pair0(dial=addr) as s1:
        wait_pipe_len(s0, 1)
        wait_pipe_len(s1, 1)
        p0 = s0.pipes[0]
        p1 = s1.pipes[0]
        assert p0.scheme == "inproc"
        assert p1.scheme == "inproc"


@pytest.mark.asyncio
async def test_v2_surveyor0_asurvey():
    """Verify v2.Surveyor0.asurvey collects responses until the survey times out."""
    import asyncio

    addr = random_addr()
    with v2.Surveyor0(listen=addr, recv_timeout=FAST_TIMEOUT) as surv:
        with v2.Respondent0(dial=addr, recv_timeout=FAST_TIMEOUT) as resp:
            wait_pipe_len(surv, 1)
            wait_pipe_len(resp, 1)

            async def responder():
                q = await resp.arecv()
                assert q == b"who-is-up"
                await resp.asend(b"node-1")

            t = asyncio.create_task(responder())
            results = await surv.asurvey(b"who-is-up", timeout=80)
            await t
            assert results == [b"node-1"]


@pytest.mark.asyncio
async def test_v2_rep0_service():
    """Verify v2.Rep0Service serves v2.Req0 clients on a v2.Rep0."""
    import asyncio

    addr = random_addr()
    async with v2.Rep0Service(addr, workers=2) as service:
        assert type(service._socket) is v2.Rep0

        async def handle_one():
            async for req in service:
                await req.reply(b"v2-echo:" + req.data)
                break

        worker = asyncio.create_task(handle_one())
        with v2.Req0(dial=addr, recv_timeout=FAST_TIMEOUT) as client:
            wait_pipe_len(client, 1)
            await client.asend(b"ping")
            reply = await client.arecv()
            assert reply == b"v2-echo:ping"
        await worker

    # Negative control: invalid socket type
    with pytest.raises(TypeError, match="Expected a pynng.v2.nng.Rep0 socket, got str"):
        v2.Rep0Service(socket="not-a-socket")


@pytest.mark.parametrize(
    "proto_cls,raw_cls",
    [
        (v2.Bus0, v2.RawBus0),
        (v2.Pair0, v2.RawPair0),
        (v2.Pair1, v2.RawPair1),
        (v2.Push0, v2.RawPush0),
        (v2.Pull0, v2.RawPull0),
        (v2.Pub0, v2.RawPub0),
        (v2.Sub0, v2.RawSub0),
        (v2.Req0, v2.RawReq0),
        (v2.Rep0, v2.RawRep0),
        (v2.Surveyor0, v2.RawSurveyor0),
        (v2.Respondent0, v2.RawRespondent0),
    ],
)
def test_v2_raw_sockets(proto_cls, raw_cls):
    """Verify raw=True and the Raw* subclasses open raw v2 sockets."""
    assert raw_cls.__bases__ == (proto_cls,)
    with proto_cls() as cooked, proto_cls(raw=True) as raw_kw, raw_cls() as raw_sub:
        assert (cooked.raw, raw_kw.raw, raw_sub.raw) == (False, True, True)


def test_v2_raw_pair0_message_flow():
    """A raw v2 socket sends and receives messages."""
    name = random_addr()
    with (
        v2.RawPair0(listen=name, recv_timeout=FAST_TIMEOUT) as raw,
        v2.Pair0(dial=name, recv_timeout=FAST_TIMEOUT) as cooked,
    ):
        wait_pipe_len(raw, 1)
        cooked.send(b"to-raw")
        msg = raw.recv_msg()
        assert msg.bytes == b"to-raw"
        raw.send_msg(v2.Message(b"to-cooked"))
        assert cooked.recv() == b"to-cooked"


def test_v2_abstract_sockaddr():
    """Verify a v2 abstract address maps to AbstractAddr, not v1's ZTAddr."""
    from pynng._nng_v2 import ffi as ffi2, lib as lib2

    sa = ffi2.new("nng_sockaddr *")
    sa[0].s_family = lib2.NNG_AF_ABSTRACT
    addr = pynng.sockaddr._nng_sockaddr(sa, lib=lib2)
    assert type(addr) is pynng.sockaddr.AbstractAddr


def test_v2_device_sync_and_cross_version_error():
    """Verify device() forwards between v2 raw sockets, refusing cross-version ones."""
    front_addr = random_addr()
    back_addr = random_addr()
    with v2.Rep0(raw=True, listen=front_addr) as front, v2.Req0(
        raw=True, listen=back_addr
    ) as back, v2.Req0(dial=front_addr, recv_timeout=FAST_TIMEOUT) as req, v2.Rep0(
        dial=back_addr, recv_timeout=FAST_TIMEOUT
    ) as rep:
        wait_pipe_len(front, 1)
        wait_pipe_len(back, 1)

        errors = []

        def run_dev():
            try:
                v2.device(front, back)
            except pynng.Closed:
                pass
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=run_dev, daemon=True)
        t.start()

        req.send(b"v2-proxy-req")
        assert rep.recv() == b"v2-proxy-req"
        rep.send(b"v2-proxy-rep")
        assert req.recv() == b"v2-proxy-rep"

        front.close()
        back.close()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert errors == []

    # Cross-version negative control
    with pynng.Pair0(raw=True) as s_v1, v2.Pair0(raw=True) as s_v2:
        with pytest.raises(ValueError, match="different nng versions"):
            pynng.device(s_v1, s_v2)


@pytest.mark.asyncio
async def test_v2_adevice_async():
    """Verify adevice() forwards messages between v2 raw sockets asynchronously."""
    import asyncio

    front_addr = random_addr()
    back_addr = random_addr()
    with v2.Rep0(raw=True, listen=front_addr) as front, v2.Req0(
        raw=True, listen=back_addr
    ) as back, v2.Req0(dial=front_addr, recv_timeout=FAST_TIMEOUT) as req, v2.Rep0(
        dial=back_addr, recv_timeout=FAST_TIMEOUT
    ) as rep:
        wait_pipe_len(front, 1)
        wait_pipe_len(back, 1)

        dev_task = asyncio.create_task(v2.adevice(front, back))
        try:
            await req.asend(b"async-v2-req")
            assert await rep.arecv() == b"async-v2-req"
            await rep.asend(b"async-v2-rep")
            assert await req.arecv() == b"async-v2-rep"
        finally:
            dev_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await dev_task


@pytest.mark.asyncio
async def test_v2_adevice_ends_with_closed_when_a_socket_closes():
    """Closing a socket ends a v2 adevice with Closed, as in v1."""
    import asyncio

    with (
        v2.Rep0(raw=True, listen=random_addr()) as front,
        v2.Req0(raw=True, listen=random_addr()) as back,
    ):
        dev_task = asyncio.create_task(v2.adevice(front, back))
        await asyncio.sleep(0.05)
        front.close()
        with pytest.raises(pynng.Closed):
            await asyncio.wait_for(dev_task, 5)


def test_v2_device_accepts_v2_nng_socket_handles():
    """v2.device accepts a raw v2 nng_socket and rejects a v1 one."""
    front_addr = random_addr()
    back_addr = random_addr()
    with (
        v2.Rep0(raw=True, listen=front_addr) as front,
        v2.Req0(raw=True, listen=back_addr) as back,
        v2.Req0(dial=front_addr, recv_timeout=FAST_TIMEOUT) as req,
        v2.Rep0(dial=back_addr, recv_timeout=FAST_TIMEOUT) as rep,
    ):
        wait_pipe_len(front, 1)
        wait_pipe_len(back, 1)
        errors = []

        def run_dev():
            try:
                v2.device(front.socket, back)
            except pynng.Closed:
                pass
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=run_dev, daemon=True)
        t.start()
        req.send(b"by-handle")
        assert rep.recv() == b"by-handle"
        rep.send(b"reply")
        assert req.recv() == b"reply"
        front.close()
        back.close()
        t.join(timeout=2.0)
        assert not t.is_alive()
        assert errors == []

    with pynng.Pair0(raw=True) as s_v1, v2.Pair0(raw=True) as s_v2:
        with pytest.raises(ValueError, match="different nng version"):
            v2.device(s_v2, s_v1.socket)
        with pytest.raises(ValueError, match="different nng version"):
            pynng.device(s_v1.socket, s_v2)


def test_v2_stats_counters_after_message_flow():
    """Verify v2 stats report real socket counters."""
    addr = random_addr()
    with (
        v2.Pair1(listen=addr) as s0,
        v2.Pair1(dial=addr, recv_timeout=FAST_TIMEOUT) as s1,
    ):
        wait_pipe_len(s0, 1)
        for payload in (b"hi", b"there"):
            s0.send(payload)
            assert s1.recv() == payload

        assert s0.stat("tx_msgs") == 2
        assert s0.stat("tx_bytes") == 7
        assert s1.stat("rx_msgs") == 2
        assert s0.stat("pipes") == 1
        assert s0.stat("protocol") == "pair1"

        tx = s0.stats().find("tx_msgs")
        assert (tx.value, tx.type_name, tx.unit_name) == (2, "counter", "messages")

        by_handle = v2.socket_stats(s0.socket)
        assert by_handle.find("tx_msgs").value == 2
        assert by_handle.find("id").value == s0.socket.id

        root = v2.stats()
        ids = {
            node["id"].value
            for node in root.find_all("socket")
            if node.type_name == "scope"
        }
        assert {s0.socket.id, s1.socket.id} <= ids


@pytest.mark.requires_tls("v1", "v2")
def test_v2_tls_endpoints_and_urls():
    """Verify TLS on v2 endpoints, with a v1 TLSConfig on the client."""
    srv_cfg, cli_cfg = _tls_configs(v2.TLSConfig, pynng.TLSConfig)

    with (
        v2.Pair0(recv_timeout=FAST_TIMEOUT, send_timeout=FAST_TIMEOUT) as srv,
        v2.Pair0(recv_timeout=FAST_TIMEOUT, send_timeout=FAST_TIMEOUT) as cli,
    ):
        listener = srv.listen("tls+tcp://127.0.0.1:0", tls_config=srv_cfg)
        assert listener.tls_config is srv_cfg
        port = _bound_port(listener)
        assert port > 0
        assert listener.url == f"tls+tcp://127.0.0.1:{port}"

        dialer = cli.dial(f"tls+tcp://127.0.0.1:{port}", tls_config=cli_cfg)
        assert dialer.tls_config is cli_cfg
        assert dialer.url == f"tls+tcp://127.0.0.1:{port}"

        cli.send(b"tls-v2-payload")
        assert srv.recv() == b"tls-v2-payload"
        srv.send(b"tls-v2-reply")
        assert cli.recv() == b"tls-v2-reply"


@pytest.mark.requires_tls
def test_v2_socket_tls_config_skips_endpoints_without_tls():
    """A socket-level TLS config applies only to endpoints whose transport has TLS."""
    srv_cfg, cli_cfg = _tls_configs(v2.TLSConfig, v2.TLSConfig)

    with (
        v2.Bus0(
            tls_config=srv_cfg, listen="tcp://127.0.0.1:0", recv_timeout=MEDIUM_TIMEOUT
        ) as srv,
        v2.Bus0(tls_config=cli_cfg, recv_timeout=MEDIUM_TIMEOUT) as cli,
    ):
        (tcp_listener,) = srv.listeners
        assert tcp_listener.tls_config is None
        inproc_listener = srv.listen(random_addr())
        assert inproc_listener.tls_config is None

        tls_listener = srv.listen("tls+tcp://127.0.0.1:0")
        assert tls_listener.tls_config is srv_cfg

        # An explicit config on a transport without TLS still fails.
        with pytest.raises(pynng.NotSupported):
            srv.listen("tcp://127.0.0.1:0", tls_config=srv_cfg)

        tcp_dialer = cli.dial(
            f"tcp://127.0.0.1:{_bound_port(tcp_listener)}", block=True
        )
        assert tcp_dialer.tls_config is None
        tls_dialer = cli.dial(
            f"tls+tcp://127.0.0.1:{_bound_port(tls_listener)}", block=True
        )
        assert tls_dialer.tls_config is cli_cfg
        wait_pipe_len(srv, 2)
        wait_pipe_len(cli, 2)

        assert sorted(pipe.scheme for pipe in srv.pipes) == ["tcp", "tls+tcp"]
        # bus0 sends each message to every peer, so one arrives on each pipe.
        cli.send(b"payload")
        msgs = [srv.recv_msg(), srv.recv_msg()]
        assert [m.bytes for m in msgs] == [b"payload", b"payload"]
        assert sorted(m.pipe.scheme for m in msgs) == ["tcp", "tls+tcp"]


def test_v2_endpoint_tls_config_getter_without_tls():
    """Endpoint tls_config is None without a TLSConfig, never a raw pointer."""
    with v2.Pair0() as srv, v2.Pair0() as cli:
        tcp_listener = srv.listen("tcp://127.0.0.1:0")
        assert tcp_listener.tls_config is None
        assert cli.dial(random_addr(), start=False).tls_config is None
        assert srv.listen("tls+tcp://127.0.0.1:0", start=False).tls_config is None


def test_v2_endpoint_url_is_not_truncated():
    """Dialer.url and Listener.url return URLs of any length."""
    name = "inproc://" + "n" * 400
    with v2.Pair0() as srv, v2.Pair0() as cli:
        assert srv.listen(name, start=False).url == name
        assert cli.dial(name, start=False).url == name


def test_v2_dialer_listener_start():
    """dial/listen with start=False create endpoints that start later."""
    name = random_addr()
    with v2.Pair0(recv_timeout=FAST_TIMEOUT) as srv, v2.Pair0() as cli:
        listener = srv.listen(name, start=False)
        dialer = cli.dial(name, start=False)
        assert list(srv.pipes) == []
        listener.start()
        dialer.start()
        wait_pipe_len(srv, 1)
        cli.send(b"started")
        assert srv.recv() == b"started"


def _strings_reachable(obj, seen=None):
    """Every str reachable from obj through its attributes and containers."""
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return []
    seen.add(id(obj))
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, bytes):
        return [obj.decode("latin-1")]
    children = []
    if isinstance(obj, dict):
        children = list(obj.keys()) + list(obj.values())
    elif isinstance(obj, (list, tuple, set, frozenset)):
        children = list(obj)
    if hasattr(obj, "__dict__"):
        children += list(vars(obj).values())
    for slot in getattr(type(obj), "__slots__", ()):
        if hasattr(obj, slot):
            children.append(getattr(obj, slot))
    found = []
    for child in children:
        found.extend(_strings_reachable(child, seen))
    return found


@pytest.mark.requires_tls
@pytest.mark.parametrize("module_name", ["v1", "v2"])
def test_tls_config_does_not_keep_secrets(module_name):
    """A TLSConfig does not keep its private key or password."""
    from test_tls import SERVER_CERT, SERVER_KEY

    cls = v2.TLSConfig if module_name == "v2" else pynng.TLSConfig
    cfg = cls(cls.MODE_SERVER, own_key_string=SERVER_KEY, own_cert_string=SERVER_CERT)
    assert [s for s in _strings_reachable(cfg) if "PRIVATE KEY" in s] == []


@pytest.mark.requires_tls("v1", "v2")
def test_tls_config_has_the_same_settings_for_v1_and_v2():
    """One TLSConfig authenticates the same way on v1 and v2 endpoints."""
    srv1_cfg, _ = _tls_configs(pynng.TLSConfig, pynng.TLSConfig)
    srv2_cfg, cli_cfg = _tls_configs(v2.TLSConfig, pynng.TLSConfig)
    cli_cfg.set_auth_mode(pynng.TLSConfig.AUTH_MODE_REQUIRED)

    with (
        pynng.Pair0(
            tls_config=srv1_cfg,
            listen="tls+tcp://127.0.0.1:0",
            recv_timeout=MEDIUM_TIMEOUT,
        ) as srv1,
        v2.Pair0(recv_timeout=MEDIUM_TIMEOUT) as srv2,
    ):
        port1 = py_socket.ntohs(srv1.listeners[0].local_address.port)
        port2 = _bound_port(srv2.listen("tls+tcp://127.0.0.1:0", tls_config=srv2_cfg))
        with (
            pynng.Pair0(
                tls_config=cli_cfg,
                dial=f"tls+tcp://127.0.0.1:{port1}",
                send_timeout=MEDIUM_TIMEOUT,
            ) as cli1,
            v2.Pair0(send_timeout=MEDIUM_TIMEOUT) as cli2,
        ):
            cli2.dial(f"tls+tcp://127.0.0.1:{port2}", tls_config=cli_cfg, block=True)
            cli1.send(b"v1")
            assert srv1.recv() == b"v1"
            cli2.send(b"v2")
            assert srv2.recv() == b"v2"


@pytest.mark.requires_tls("v1", "v2")
def test_tls_config_refused_where_its_settings_diverged():
    """A setter that fails for one version makes that version refuse the config."""
    srv1_cfg, _ = _tls_configs(pynng.TLSConfig, pynng.TLSConfig)
    srv2_cfg, cli_cfg = _tls_configs(v2.TLSConfig, pynng.TLSConfig)

    with (
        pynng.Pair0(
            tls_config=srv1_cfg,
            listen="tls+tcp://127.0.0.1:0",
            recv_timeout=MEDIUM_TIMEOUT,
        ) as srv1,
        v2.Pair0(recv_timeout=MEDIUM_TIMEOUT) as srv2,
    ):
        port1 = py_socket.ntohs(srv1.listeners[0].local_address.port)
        port2 = _bound_port(srv2.listen("tls+tcp://127.0.0.1:0", tls_config=srv2_cfg))
        with v2.Pair0(send_timeout=MEDIUM_TIMEOUT) as cli2:
            cli2.dial(f"tls+tcp://127.0.0.1:{port2}", tls_config=cli_cfg, block=True)
            cli2.send(b"v2")
            assert srv2.recv() == b"v2"

            # The v2 config is now in use, so nng refuses to change it; the v1
            # config is not, so nng changed that one.
            with pytest.raises(pynng.Busy):
                cli_cfg.set_server_name("localhost")
            with (
                v2.Pair0() as cli3,
                pytest.raises(RuntimeError, match="different settings"),
            ):
                cli3.dial(f"tls+tcp://127.0.0.1:{port2}", tls_config=cli_cfg)

        with pynng.Pair0(
            tls_config=cli_cfg,
            dial=f"tls+tcp://127.0.0.1:{port1}",
            send_timeout=MEDIUM_TIMEOUT,
        ) as cli1:
            cli1.send(b"v1")
            assert srv1.recv() == b"v1"


def test_tls_config_created_before_v2_import_is_refused_by_v2(tmp_path):
    """A v1 TLSConfig made before pynng.v2 was imported cannot reach v2."""
    import subprocess
    import sys

    script = (
        "import pynng\n"
        "cfg = pynng.TLSConfig(pynng.TLSConfig.MODE_CLIENT)\n"
        "import pynng.v2 as v2\n"
        "with v2.Pair0() as s:\n"
        "    try:\n"
        "        s.dial('tls+tcp://127.0.0.1:1', tls_config=cfg, block=False)\n"
        "    except RuntimeError as exc:\n"
        "        print('refused:', exc)\n"
    )
    # Run outside the source tree, so the child imports the installed pynng
    # (or PYTHONPATH) and not the uncompiled checkout through sys.path[0].
    out = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.startswith("refused: This TLSConfig was created before")


@pytest.mark.parametrize(
    "versions,v1_has,v2_has,runs",
    [
        (("v1", "v2"), False, True, False),
        (("v1", "v2"), True, False, False),
        (("v1", "v2"), True, True, True),
        (("v2",), False, True, True),
        ((), False, True, True),
        ((), False, False, False),
    ],
)
def test_tls_gate_requires_every_version_the_test_uses(versions, v1_has, v2_has, runs):
    """requires_tls("v1", "v2") skips unless both versions have TLS."""
    from conftest import _tls_skip_reason

    assert (_tls_skip_reason(versions, v1_has, v2_has) is None) is runs


@pytest.mark.asyncio
@pytest.mark.parametrize("mod", [pynng, v2], ids=["v1", "v2"])
async def test_rep0_service_borrowed_socket_is_restored(mod):
    """Rep0Service(socket=, address=) closes its listener and restores timeouts."""
    addr = random_addr()
    with mod.Rep0(recv_timeout=1234, send_timeout=2345) as sock:
        service = mod.Rep0Service(
            addr, socket=sock, workers=1, recv_timeout=100, send_timeout=200
        )
        for round_no in range(2):
            async with service:
                assert (sock.recv_timeout, sock.send_timeout) == (100, 200)
                assert len(sock.listeners) == 1
                with mod.Req0(dial=addr, recv_timeout=MEDIUM_TIMEOUT) as client:
                    await client.asend(b"ping-%d" % round_no)
                    async for req in service:
                        await req.reply(b"pong:" + req.data)
                        break
                    assert await client.arecv() == b"pong:ping-%d" % round_no
            assert (sock.recv_timeout, sock.send_timeout) == (1234, 2345)
            assert list(sock.listeners) == []
        sock.send_timeout = 10
        assert sock.send_timeout == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("mod", [pynng, v2], ids=["v1", "v2"])
async def test_rep0_service_borrowed_socket_restored_on_startup_failure(mod):
    """A failed start leaves a borrowed socket as it was."""
    addr = random_addr()
    with mod.Rep0(listen=addr) as holder, mod.Rep0(recv_timeout=1234) as sock:
        service = mod.Rep0Service(addr, socket=sock, recv_timeout=100)
        with pytest.raises(pynng.AddressInUse):
            async with service:
                pass
        assert sock.recv_timeout == 1234
        assert list(sock.listeners) == []
        assert len(holder.listeners) == 1


def test_rep0_service_socket_must_be_a_cooked_rep0_of_its_version():
    """Rep0Service(socket=) validates the socket type and version."""
    with (
        v2.Pub0() as pub,
        pynng.Rep0() as rep_v1,
        v2.Rep0() as rep_v2,
        v2.RawRep0() as raw,
    ):
        with pytest.raises(ValueError, match="address or socket"):
            v2.Rep0Service()
        with pytest.raises(TypeError, match="pynng.v2.nng.Rep0"):
            v2.Rep0Service(socket=pub)
        with pytest.raises(TypeError, match="pynng.v2.nng.Rep0"):
            v2.Rep0Service(socket=rep_v1)
        with pytest.raises(TypeError, match="pynng.nng.Rep0"):
            pynng.Rep0Service(socket=rep_v2)
        with pytest.raises(ValueError, match="raw"):
            v2.Rep0Service(socket=raw)
        assert v2.Rep0Service(socket=rep_v2)._socket is rep_v2
        assert pynng.Rep0Service(socket=rep_v1)._socket is rep_v1
