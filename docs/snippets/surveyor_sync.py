from pynng import Surveyor0, Respondent0, Timeout

import time

address = 'tcp://127.0.0.1:13131'

with Surveyor0(listen=address) as surveyor, \
        Respondent0(dial=address) as responder1, \
        Respondent0(dial=address) as responder2:
    # give time for connections to happen
    time.sleep(0.1)
    surveyor.survey_time = 500
    surveyor.send(b'who wants to party?')
    # usually these would be in another thread or process, ya know?
    responder1.recv()
    responder2.recv()
    responder1.send(b'me me me!!!')
    responder2.send(b'I need to sit this one out.')

    # accept responses until the survey is finished.
    while True:
        try:
            response = surveyor.recv()
            if response == b'me me me!!!':
                print('all right, someone is ready to party!')
            elif response == b'I need to sit this one out.':
                print('Too bad, someone is not ready to party.')
        except Timeout:
            print('survey is OVER!  Time for bed.')
            break


