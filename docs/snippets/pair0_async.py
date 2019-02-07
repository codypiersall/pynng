from trio import run
from pynng import Pair0


async def send_and_recv():
    address = 'tcp://127.0.0.1:13131'
    # in real code you should also pass recv_timeout and/or send_timeout
    with Pair0(listen=address) as s0, Pair0(dial=address) as s1:
        await s0.asend(b'hello s1')
        print(await s1.arecv())  # prints b'hello s1'
        await s1.asend(b'hi old buddy s0, great to see ya')
        print(await s0.arecv())  # prints b'hi old buddy s0, great to see ya

run(send_and_recv)
