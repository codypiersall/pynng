"""
Demonstrate how to use a pipeline socket.

This pattern is useful for solving producer/consumer problems, including load-balancing. 
Messages flow from the push side to the pull side.
If multiple peers are connected, the pattern attempts to distribute fairly.

"""
import pynng
import curio

address = "ipc:///tmp/pipeline.ipc"


async def node0(sock):
    async def recv_eternally():
        while True:
            msg = await sock.arecv_msg()
            content = msg.bytes.decode()
            print(f'NODE0: RECEIVED "{content}"')

    sock.listen(address)
    return await curio.spawn(recv_eternally)


async def node1(message):
    with pynng.Push0() as sock:
        sock.dial(address)
        print(f'NODE1: SENDING "{message}"')
        await sock.asend(message.encode())
        await curio.sleep(1)  # wait for messages to flush before shutting down


async def main():
    with pynng.Pull0() as pull:

        n0 = await node0(pull)
        await curio.sleep(1)

        await node1("Hello, World!")
        await node1("Goodbye.")

        # another way to send
        async with curio.TaskGroup(wait=all) as g:
            for msg in ["A", "B", "C", "D"]:
                await g.spawn(node1, msg)

        await n0.cancel()


if __name__ == "__main__":
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass