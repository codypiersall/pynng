from pynng import Pair1

address = 'tcp://127.0.0.1:12343'
with Pair1(listen=address, polyamorous=True) as s0, \
        Pair1(dial=address, polyamorous=True) as s1, \
        Pair1(dial=address, polyamorous=True) as s2:
    s1.send(b'hello from s1')
    s2.send(b'hello from s2')
    msg1 = s0.recv_msg()
    msg2 = s0.recv_msg()
    print(msg1.bytes)  # prints b'hello from s1'
    print(msg2.bytes)  # prints b'hello from s2'
    msg1.pipe.send(b'hey s1')
    msg2.pipe.send(b'hey s2')
    print(s2.recv())  # prints b'hey s2'
    print(s1.recv())  # prints b'hey s1'
