"""
 PyNNG example of Pub/Sub with both normal single thread subscriber
 extended from what is the docs
   https://pynng.readthedocs.io/en/latest/core.html#available-#

Publisher/Subscriber has one socket that publishes messages and
any number of subscribers that listen to that publisher.
Subscribers can subscribe to a TOPIC, and they will only deliver those topics
to the rest of the application (under hood they still receive all msgs, but
will discard those that are not of right topic)

 this is the subscriber part and should be run in conjunction with pynng_pubTest.py

"""
import time
from pynng import Pub0, Sub0, Timeout

address = 'tcp://127.0.0.1:31313'
with Sub0(dial=address, recv_timeout=1000) as sub0, \
        Sub0(dial=address, recv_timeout=1000) as sub1, \
        Sub0(dial=address, recv_timeout=1000) as sub2, \
        Sub0(dial=address, recv_timeout=1000) as sub3:

    sub0.subscribe(b'wolf')
    sub1.subscribe(b'puppy')
    # The empty string matches everything!
    sub2.subscribe(b'')
    # we're going to send two messages before receiving anything, and this is
    # the only socket that needs to receive both messages.
    sub2.recv_buffer_size = 2
    # sub3 is not subscribed to anything
    # make sure everyone is connected
    print("all set, wait a moment then Publish")
    time.sleep(1)

    while True:
        print("sub0 rcv:",sub0.recv())  # prints b'wolf...' since that is the matching message
        print("sub1 rcv:",sub1.recv())  # prints b'puppy...' since that is the matching message

    # sub2 will receive all messages (since empty string matches everything)
        print("sub2 rcv:",sub2.recv())  # prints b'puppy...' since it was sent first
        print("sub2 rcv:",sub2.recv())  # prints b'wolf...' since it was sent second

        try:
            sub3.recv()
            assert False, 'never gets here since sub3 is not subscribed'
        except Timeout:
            print('got a Timeout since sub3 had no subscriptions')
        time.sleep(1)
