import time


def _started(sock):
    # A pipe is in Socket.pipes from NNG_PIPE_EV_ADD_PRE, before the protocol
    # starts it, and a broadcast protocol (Pub0, Surveyor0) drops a message
    # sent to a pipe it has not started. ADD_POST comes after the start.
    states = sock._pipe_states
    return all(
        (state := states.get(pipe.id)) is not None and state.added
        for pipe in sock.pipes
    )


def wait_pipe_len(sock, expected, timeout=10):
    """
    Wait up to ``timeout`` seconds for ``sock.pipes`` to have ``expected``
    pipes, all of which the protocol has started.  This prevents hardcoding
    sleep times, which should be pretty small for local development but
    potentially pretty large for CI runs.

    """
    now = time.monotonic()
    later = now + timeout
    while time.monotonic() < later and not (
        len(sock.pipes) == expected and _started(sock)
    ):
        time.sleep(0.0005)
    if len(sock.pipes) != expected or not _started(sock):
        raise TimeoutError(
            f"Waiting for {expected} started pipes, but have {len(sock.pipes)} pipes"
        )
