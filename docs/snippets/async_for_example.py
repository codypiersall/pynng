import pynng
import trio

NUM_MESSAGES = 5


async def receiver(socket, received, scope):
    async for msg in socket:
        print(f'Received: {msg}')
        received.append(msg)
        if len(received) >= NUM_MESSAGES:
            scope.cancel()
            return


async def sender(address):
    async with pynng.Pair0(dial=address) as s:
        for i in range(NUM_MESSAGES):
            await s.asend(f'message {i}'.encode())
            await trio.sleep(0.1)


async def main():
    address = 'inproc://async-for-demo'
    received = []
    async with pynng.Pair0(listen=address, recv_timeout=2000) as s:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(receiver, s, received, nursery.cancel_scope)
            nursery.start_soon(sender, address)
    print(f'Done: received {len(received)} messages')


trio.run(main)
