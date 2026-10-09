import asyncio
import pynng

NUM_MESSAGES = 5


async def receiver(socket, received):
    async for msg in socket:
        print(f'Received: {msg}')
        received.append(msg)
        if len(received) >= NUM_MESSAGES:
            return


async def sender(address):
    async with pynng.Pair0(dial=address) as s:
        for i in range(NUM_MESSAGES):
            await s.asend(f'message {i}'.encode())
            await asyncio.sleep(0.1)


async def main():
    address = 'inproc://async-for-asyncio-demo'
    received = []
    async with pynng.Pair0(listen=address, recv_timeout=2000) as s:
        await asyncio.gather(receiver(s, received), sender(address))
    print(f'Done: received {len(received)} messages')


asyncio.run(main())
