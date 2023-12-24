import time


def wait_pipe_len(sock, expected, timeout=10):
    """
    Wait up to ``timeout`` seconds for the length of sock.pipes to become
    ``expected`` value.  This prevents hardcoding sleep times, which should be
    pretty small for local development but potentially pretty large for CI
    runs.

    """
    now = time.time()
    later = now + timeout
    while time.time() < later and len(sock.pipes) != expected:
        time.sleep(0.0005)
    if len(sock.pipes) != expected:
        raise TimeoutError(f'Waiting for {expected} pipes, but have {len(sock.pipes)} pipes')


