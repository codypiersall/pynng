"""
 PyNNG example of Pub/Sub with both normal and async versions
 extended from what is the docs
   https://pynng.readthedocs.io/en/latest/core.html#available-#

Publisher/Subscriber has one socket that publishes messages and
any number of subscribers that listen to that publisher.
Subscribers can subscribe to a TOPIC, and they will only deliver those topics
to the rest of the application (under hood they still receive all msgs, but
will discard those that are not of right topic)

 this is the publisher part and should be run in conjunction with one of the
 pynng_subTest/_subTestAsync examples

"""
import time
from pynng import Pub0, Sub0, Timeout
import trio

address = 'tcp://127.0.0.1:31313'

wolfStr = "wolf: that is a big dog "
puppyStr = "puppy: that is a cute puppy "

def pubLoop_Sync(pub):
    print("sync publisher")
    for i in range(120):
        print("publish %d"%(i))
        sp = puppyStr+str(i)
        pub.send(sp.encode())
        sw = wolfStr+str(i)
        pub.send(sw.encode())
        time.sleep(1)


async def asend(pub, msg):
    pub.asend(msg)

async def pubLoop_Async(pub):
    print("Trio Async Publisher")
    for i in range(120):
        print("async publish %d"%(i))
        sp = puppyStr+str(i)
        await pub.asend(sp.encode())
        sw = wolfStr+str(i)
        await pub.asend(sw.encode())
        await trio.sleep(0.75)
    pass

if __name__ == "__main__":

    with Pub0(listen=address) as pub:
        print("Pub started, wait for subs")
        time.sleep(2)

        #pubLoop_Sync(pub)
        trio.run(pubLoop_Async, pub)
        pub.close()
