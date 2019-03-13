import time
from pynng import Pub0, Sub0, Timeout

address = 'tcp://127.0.0.1:31313'
with Pub0(listen=address) as pub, \
        Sub0(dial=address, recv_timeout=100) as sub0, \
        Sub0(dial=address, recv_timeout=100) as sub1, \
        Sub0(dial=address, recv_timeout=100) as sub2, \
        Sub0(dial=address, recv_timeout=100) as sub3:

    sub0.subscribe(b'wolf')
    sub1.subscribe(b'puppy')
    # The empty string matches everything!
    sub2.subscribe(b'')
    # we're going to send two messages before receiving anything, and this is
    # the only socket that needs to receive both messages.
    sub2.recv_buffer_size = 2
    # sub3 is not subscribed to anything
    # make sure everyone is connected
    time.sleep(0.05)

    pub.send(b'puppy: that is a cute dog')
    pub.send(b'wolf: that is a big dog')

    print(sub0.recv())  # prints b'wolf...' since that is the matching message
    print(sub1.recv())  # prints b'puppy...' since that is the matching message

    # sub2 will receive all messages (since empty string matches everything)
    print(sub2.recv())  # prints b'puppy...' since it was sent first
    print(sub2.recv())  # prints b'wolf...' since it was sent second

    try:
        sub3.recv()
        assert False, 'never gets here since sub3 is not subscribed'
    except Timeout:
        print('got a Timeout since sub3 had no subscriptions')




