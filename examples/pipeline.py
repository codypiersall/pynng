"""
Demonstrate how to use a pipeline socket.

This pattern is useful for solving producer/consumer problems, including load-balancing.
Messages flow from the push side to the pull side.
If multiple peers are connected, the pattern attempts to distribute fairly.

"""

import pynng
import trio

address = "ipc:///tmp/pipeline.ipc"


async def node0(sock):
    async def recv_eternally():
        while True:
            try:
                msg = await sock.arecv_msg()
            except pynng.Timeout:
                break
            content = msg.bytes.decode()
            print(f'NODE0: RECEIVED "{content}"')

    return await recv_eternally()


async def node1(message):
    with pynng.Push0() as sock:
        sock.dial(address)
        print(f'NODE1: SENDING "{message}"')
        await sock.asend(message.encode())
        await trio.sleep(1)  # wait for messages to flush before shutting down


async def main():
    # open a pull socket, and then open multiple Push sockets to push to them.
    with pynng.Pull0(listen=address, recv_timeout=200) as pull:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(node0, pull)
            for msg in ["A", "B", "C", "D"]:
                nursery.start_soon(node1, msg)


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass
