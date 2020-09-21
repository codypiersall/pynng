Examples
========

This directory contains examples on using pynng for different tasks.

* [`pair0.py`](./pair0.py): Demonstrates the basic bi-directional connection,
  pair0.  Adapted from [nng pair
  example](https://nanomsg.org/gettingstarted/nng/pair.html).
* [`pair1_async.py`](./pair1_async.py): Demonstrates a polyamorous pair1
  connection.

Several more examples are described in [pynng.ReadTheDocs](https://pynng.readthedocs.io/en/latest/core.html#available-protocols)
  and implemented here

* [`pair1_PolyAsync.py`](./pair1_PolyAsync.py): More elaborate demo of 
  polyamorous pair1 
* [`pubsub_1SingleApp.py`](./pubsub_1SingleApp.py): single app showing publish and subscribe
* [`pubsub_2publishAsync.py`](./pubsub_2publishAsync.py): pub/sub publisher side using Trio async
* [`pubsub_2subscribe.py`](./pubsub_2subscribe.py): pub/sub subscriber side, no threading
* [`pubsub_2subscribeAsync.py`](./pubsub_2subscribeAsync.py): pub/sub subscriber using Trio async

Adding an Example
-----------------

More examples are welcome.  To add an example:
1. create a new file in this directory that demonstrates what needs to be
   demonstrated
2. Make sure there is a docstring in the file that describes what it is
   demonstrating.  Add as much detail as is needed.  Show example in the
   docstring as well.
3. Add a short description of what the example does to the list of descriptions
   in this file.  Keep the list in alphabetical order.

Don't call out to third-party code if you can help it.  Keep examples simple.
If you are adding an async example, use
[trio](https://trio.readthedocs.io/en/latest/).
