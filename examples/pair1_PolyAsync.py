"""
Demonstrate how to use a pair1 polyamorous sockets with Trio async
 derived from the docs page
  https://pynng.readthedocs.io/en/latest/core.html#available-protocols

Pair1 sockets are similar to pair0 sockets.  The difference is that while pair0
supports only a single connection, pair1 sockets support _n_ one-to-one
connections.

This program demonstrates how to use pair1 sockets.  The key differentiator is
that with pair1 sockets, you must always specify the *pipe* that you want to
use for the message.

"""

# pynng mod of async polyamorus example in ReadTheDocs
# from the docs page https://pynng.readthedocs.io/en/latest/core.html#available-protocols
#
# Pair1 allows single Server/Listener to connect bi-directionally with multiple Client/Dialers
# it does NOT operate as a Publisher in that a listner.send() goes to ??
#

import sys, traceback
from pynng import Pair1, Timeout
print("begin Pair 1 polyamorous test")

address = 'tcp://127.0.0.1:12343'
with Pair1(listen=address, polyamorous=True, recv_timeout=100) as s0, \
        Pair1(dial=address, polyamorous=True, recv_timeout=100) as s1, \
        Pair1(dial=address, polyamorous=True, recv_timeout=100) as s2:
    print("opened all 3")
    s0.send(b'hi everybody!')
    s1.send(b'hello from s1')
    s2.send(b'hello from s2')
    print("sent all three")
    print("recv_msg on s0")
    msg1 = s0.recv_msg()
    print(msg1.bytes)  # prints b'hello from s1'

    msg2 = s0.recv_msg()
    print(msg2.bytes)  # prints b'hello from s2'
    
    print("recv on s1:")
    msg01 = s1.recv()
    print(msg01)  # prints b'hello from s1'

    try:
        print("recv on s2")
        msg02 = s2.recv()
        print(msg02)  # prints b'hello from s2'
    except Timeout:
        print("Timeout on S2 waiting to hear from s0")

    print("send single msg responses")
    msg1.pipe.send(b'hey s1')
    msg2.pipe.send(b'hey s2')
    print(s2.recv())  # prints b'hey s2'
    print(s1.recv())  # prints b'hey s1'
    
    # beyond first msg, repeats will share the Pipe but not data
    s1.send(b'more from s1')
    morMsg = s0.recv_msg()
    print("morMsg: ")
    print(morMsg.bytes)
    if morMsg.pipe == msg1.pipe:
        print ("msg1 and morMsg share pipe")
    else:
        print ("msg1 and morMsg do NOT share pipe")
    print("and msg1 still says:")
    print(msg1.bytes)
    
    print("what if s0 does recv instead of recvMsg?")
    s1.send(b'again from s1')
    more = s0.recv()
    print(more)
#    print("It works, we just dont get the Message info")
    
    print("Pair1 with both listen and dial should throw exception")
    # pynng Pair1 has no code to recognize this error, allowing both arguments
    # however the underlying Socket should throw an AddressInUse exception
    try:
        with Pair1(dial=address, listen=address, polyamorous=True, recv_timeout=100) as s3:
            s3.send(b'hello out there')
            msg = s0.recv_msg()
            print("rceve on s0")
            print(msg.bytes)
            s3.send(b'hello out there')
            msg = s3.recv_msg()
            print("rceve on s3")
            print(msg.bytes)
    except:
        print("caught something", sys.exc_info()[0])
        traceback.print_exc()#sys.exc_info()[2].print_tb()
        #raise
    
print("End Pair1 test")

        
