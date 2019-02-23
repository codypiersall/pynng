from pynng import Req0, Rep0

address = 'tcp://127.0.0.1:13131'

with Rep0(listen=address) as rep, Req0(dial=address) as req:
    req.send(b'random.random()')
    question = rep.recv()
    answer = b'4'  # guaranteed to be random
    rep.send(answer)
    print(req.recv())  # prints b'4'
