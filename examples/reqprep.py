"""
Request/Reply is used for synchronous communications where each question is responded with a single answer,
for example remote procedure calls (RPCs).
Like Pipeline, it also can perform load-balancing.
This is the only reliable messaging pattern in the suite, as it automatically will retry if a request is not matched with a response.

"""
import datetime
import pynng
import curio

DATE = "DATE"

address = "ipc:///tmp/reqrep.ipc"


async def node0(sock):
    async def response_eternally():
        while True:
            msg = await sock.arecv_msg()
            content = msg.bytes.decode()
            if DATE == content:
                print("NODE0: RECEIVED DATE REQUEST")
                date = str(datetime.datetime.now())
                await sock.asend(date.encode())

    sock.listen(address)
    return await curio.spawn(response_eternally)


async def node1():
    with pynng.Req0() as sock:
        sock.dial(address)
        print(f"NODE1: SENDING DATE REQUEST")
        await sock.asend(DATE.encode())
        msg = await sock.arecv_msg()
        print(f"NODE1: RECEIVED DATE {msg.bytes.decode()}")


async def main():
    with pynng.Rep0() as rep:
        n0 = await node0(rep)
        await curio.sleep(1)
        await node1()

        await n0.cancel()


if __name__ == "__main__":
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass