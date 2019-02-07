from pynng import Pair0
address = 'tcp://127.0.0.1:13131'
# in real code you should also pass recv_timeout and/or send_timeout
with Pair0(listen=address) as s0, Pair0(dial=address) as s1:
    s0.send(b'hello s1')
    print(s1.recv())  # prints b'hello s1'
    s1.send(b'hi old buddy s0, great to see ya')
    print(s0.recv())  # prints b'hi old buddy s0, great to see ya
