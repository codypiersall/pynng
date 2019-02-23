import time

from pynng import Bus0, Timeout

address = 'tcp://127.0.0.1:13131'
with Bus0(listen=address, recv_timeout=100) as s0, \
        Bus0(dial=address, recv_timeout=100) as s1, \
        Bus0(dial=address, recv_timeout=100) as s2:
    # let all connections be established
    time.sleep(0.05)
    s0.send(b'hello buddies')
    s1.recv()  # prints b'hello buddies'
    s2.recv()  # prints b'hello buddies'
    s1.send(b'hi s0')
    print(s0.recv())  # prints b'hi s0'
    # s2 is not directly connected to s1.
    try:
        s2.recv()
        assert False, "this is never reached"
    except Timeout:
        print('s2 is not connected directly to s1!')

