import pynng
import trio


async def main():
    async with pynng.Pair0(listen='inproc://async-with-demo') as s0:
        async with pynng.Pair0(dial='inproc://async-with-demo') as s1:
            await s0.asend(b'hello from async with!')
            msg = await s1.arecv()
            print(msg)


trio.run(main)
