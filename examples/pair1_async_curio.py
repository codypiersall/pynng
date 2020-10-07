"""
Demonstrate how to use a pair1 socket.

Pair1 sockets are similar to pair0 sockets.  The difference is that while pair0
supports only a single connection, pair1 sockets support _n_ one-to-one
connections.

This program demonstrates how to use pair1 sockets.  The key differentiator is
that with pair1 sockets, you must always specify the *pipe* that you want to
use for the message.

To use this program, you must start several nodes.  One node will be the
listener, and all other nodes will be dialers.  In one terminal, you must start
a listener:

    python pair1_async.py listen tcp://127.0.0.1:12345

And in as many separate terminals as you would like, start some dialers:

    # run in as many separate windows as you wish
    python pair1_async.py dial tcp://127.0.0.1:12345

Whenever you type into the dialer processes, whatever you type is received on
the listening process.  Whatever you type into the listening process is sent to
*all* the dialing processes.

"""

import argparse
import sys
import pynng
import curio


async def send_eternally(sock):
    """
    Eternally listen for user input in the terminal and send it on all
    available pipes.
    """
    stdin = curio.io.FileStream(sys.stdin.buffer)
    while stdin:
        line = await stdin.read(1024)
        if not line:
            break
        text = line.decode('utf-8')
        for pipe in sock.pipes:
            await pipe.asend(text.encode())        


async def recv_eternally(sock):
    while True:
        msg = await sock.arecv_msg()
        source_addr = str(msg.pipe.remote_address)
        content = msg.bytes.decode()
        print('{} says: {}'.format(source_addr, content))


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        'mode',
        help='Whether the socket should "listen" or "dial"',
        choices=['listen', 'dial'],
    )
    p.add_argument(
        'addr',
        help='Address to listen or dial; e.g. tcp://127.0.0.1:13134',
    )
    args = p.parse_args()

    with pynng.Pair1(polyamorous=True) as sock:
        async with curio.TaskGroup(wait=any) as g:
            if args.mode == 'listen':
                # the listening socket can get dialled by any number of dialers.
                # add a couple callbacks to see when the socket is receiving
                # connections.
                def pre_connect_cb(pipe):
                    addr = str(pipe.remote_address)
                    print('~~~~got connection from {}'.format(addr))

                def post_remove_cb(pipe):
                    addr = str(pipe.remote_address)
                    print('~~~~goodbye for now from {}'.format(addr))
                sock.add_pre_pipe_connect_cb(pre_connect_cb)
                sock.add_post_pipe_remove_cb(post_remove_cb)
                sock.listen(args.addr)
            else:
                sock.dial(args.addr)

            await g.spawn(recv_eternally, sock)
            await g.spawn(send_eternally, sock)



if __name__ == '__main__':
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass