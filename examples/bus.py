"""
The bus protocol is useful for routing applications, or for building fully interconnected mesh networks.
In this pattern, messages are sent to every directly connected peer.
"""
import pynng
import curio


async def node(name, listen_address, contacts):
    with pynng.Bus0() as sock:
        sock.listen(listen_address)
        await curio.sleep(1)  #  wait for peers to bind
        for contact in contacts:
            sock.dial(contact)

        await curio.sleep(1)
        # wait for connects to establish
        print(f"{name}: SENDING '{listen_address}' ONTO BUS")
        await sock.asend(listen_address.encode())

        while True:
            try:
                msg = await sock.arecv_msg()
                print(f'{name}: RECEIVED "{msg.bytes.decode()}" FROM BUS')
            except pynng.Timeout:
                print(f"{name}: Timeout")
                break


async def main():
    async with curio.TaskGroup(wait=all) as g:
        await g.spawn(
            node,
            "node0",
            "ipc:///tmp/node0.ipc",
            ["ipc:///tmp/node1.ipc", "ipc:///tmp/node2.ipc"],
            daemon=True,
        )
        await g.spawn(
            node,
            "node1",
            "ipc:///tmp/node1.ipc",
            ["ipc:///tmp/node2.ipc", "ipc:///tmp/node3.ipc"],
            daemon=True,
        )
        await g.spawn(
            node, "node2", "ipc:///tmp/node2.ipc", ["ipc:///tmp/node3.ipc"], daemon=True
        )
        await g.spawn(
            node, "node3", "ipc:///tmp/node3.ipc", ["ipc:///tmp/node0.ipc"], daemon=True
        )
        await curio.sleep(5)  # wait % seconde before stop all
        await g.join()


if __name__ == "__main__":
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass
