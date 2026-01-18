"""
pair0Async.py very simple pair of pair0 sockets doing send/receive in a trio.run

Demonstrate how to use a pair0 socket asynchronously with Trio
Pair0 is very simple 1:1 bidirectional message passing.
this demo is kinda trivial as it runs both send + receive at same time
"""


import pynng
import trio

# async function that sends a
async def send_and_recv(sender, receiver, message):
    await sender.asend(message)
    return await receiver.arecv()

with pynng.Pair0(listen='tcp://127.0.0.1:54321') as s1, \
        pynng.Pair0(dial='tcp://127.0.0.1:54321') as s2:
    # simplistic Trio async function
    received = trio.run(send_and_recv, s1, s2, b'hello there old pal!')
    print("received: ", received)
    assert received == b'hello there old pal!'
    
    
