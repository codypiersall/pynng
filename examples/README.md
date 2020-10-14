Examples
========

This directory contains examples on using pynng for different tasks.

* Pair (Two Way Radio) [`pair0.py`](./pair0.py):
   Demonstrates the basic bi-directional connection, pair0.
   Adapted from [nng pair example](https://nanomsg.org/gettingstarted/nng/pair.html).
* Polyamorous pair1 connection :  
   - [`pair1_async.py`](./pair1_async.py): Demonstrates using trio.
   - [`pair1_async_curio.py`](./pair1_async.py): Demonstrates using curio.
* Pipeline (A One-Way Pipe) :
   [`pipeline.py`](./pair1_async.py): Push/Pull adapted from [nng example](https://nanomsg.org/gettingstarted/nng/pipeline.html)
* Request/Reply (I ask, you answer) :
   [`reqprep.py`](./reqprep.py): Rep0/Req0 adapted from [nng example](https://nanomsg.org/gettingstarted/nng/pipeline.html)
* Pub/Sub (Topics & Broadcast):
   [`pubsub.py`](./pubsub.py): Pub0/Sub0 adapted from [nng example](https://nanomsg.org/gettingstarted/nng/pubsub.html)
* Survey (Everybody Votes):
   [`survey.py`](./survey.py): Surveyor0/Respondent0 adapted from [nng example](https://nanomsg.org/gettingstarted/nng/survey.html)
* Bus (Routing):
   [`bus.py`](./bus.py): Bus0 adapted from [nng example](https://nanomsg.org/gettingstarted/nng/bus.html)



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
