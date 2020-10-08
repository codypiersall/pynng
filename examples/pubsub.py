"""
This pattern is used to allow a single broadcaster to publish messages to many subscribers,
which may choose to limit which messages they receive.
"""
import datetime
import pynng
import curio

address = "ipc:///tmp/pubsub.ipc"


def get_current_date():
    return str(datetime.datetime.now())


async def server(sock):
    async def publish_eternally():
        while True:
            date = get_current_date()
            print(f"SERVER: PUBLISHING DATE  {date}")
            await sock.asend(date.encode())
            await curio.sleep(1)

    sock.listen(address)
    return await curio.spawn(publish_eternally)


async def client(name, max_msg=2):
    with pynng.Sub0() as sock:
        sock.subscribe("")
        sock.dial(address)

        while max_msg:
            msg = await sock.arecv_msg()
            print(f"CLIENT ({name}): RECEIVED  {msg.bytes.decode()}")
            max_msg -= 1


async def main():
    with pynng.Pub0() as pub:
        n0 = await server(pub)
        async with curio.TaskGroup(wait=all) as g:
            await g.spawn(client, "client0", 2)
            await g.spawn(client, "client1", 3)
            await g.spawn(client, "client2", 4)

        await n0.cancel()


if __name__ == "__main__":
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass