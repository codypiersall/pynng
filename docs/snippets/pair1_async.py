from pynng import Pair1
import trio


async def polyamorous_send_and_recv():
    address = 'tcp://127.0.0.1:12343'
    with Pair1(listen=address, polyamorous=True) as s0, \
            Pair1(dial=address, polyamorous=True) as s1, \
            Pair1(dial=address, polyamorous=True) as s2:
        await s1.asend(b'hello from s1')
        await s2.asend(b'hello from s2')
        msg1 = await s0.arecv_msg()
        msg2 = await s0.arecv_msg()
        print(msg1.bytes)  # prints b'hello from s1'
        print(msg2.bytes)  # prints b'hello from s2'
        await msg1.pipe.asend(b'hey s1')
        await msg2.pipe.asend(b'hey s2')
        print(await s2.arecv())  # prints b'hey s2'
        print(await s1.arecv())  # prints b'hey s1'

trio.run(polyamorous_send_and_recv)
