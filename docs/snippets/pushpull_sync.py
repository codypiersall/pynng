import time

from pynng import Push0, Pull0, Timeout

addr = 'tcp://127.0.0.1:31313'
with Push0(listen=addr) as push, \
        Pull0(dial=addr, recv_timeout=100) as pull0, \
        Pull0(dial=addr, recv_timeout=100) as pull1:
    pass
    # give some time to connect
    time.sleep(0.01)
    push.send(b'hi some node')
    push.send(b'hi some other node')
    print(pull0.recv())  # prints b'hi some node'
    print(pull1.recv())  # prints b'hi some other node'
    try:
        pull0.recv()
        assert False, "Cannot get here, since messages are sent round robin"
    except Timeout:
        pass


