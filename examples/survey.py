"""
The surveyor pattern is used to send a timed survey out,
responses are individually returned until the survey has expired.
This pattern is useful for service discovery and voting algorithms.
"""
import datetime
import pynng
import curio

DATE = "DATE"
address = "ipc:///tmp/survey.ipc"


def get_current_date():
    return str(datetime.datetime.now())


async def server(sock, max_survey_request=10):

    async def survey_eternally():
        nonlocal max_survey_request
        while max_survey_request:
            print(f"SERVER: SENDING DATE SURVEY REQUEST")
            await sock.asend(DATE.encode())
            while True:
                try:
                    msg = await sock.arecv_msg()
                    print(f"SERVER: RECEIVED \"{msg.bytes.decode()}\" SURVEY RESPONSE")
                except pynng.Timeout:
                    break
            print("SERVER: SURVEY COMPLETE")
            max_survey_request -= 1

    sock.listen(address)
    return await curio.spawn(survey_eternally)


async def client(name, max_survey=3):

    async def send_survey_eternally():
        nonlocal max_survey
        with pynng.Respondent0() as sock:
            sock.dial(address)
            while max_survey:
                await sock.arecv_msg()
                print(f"CLIENT ({name}): RECEIVED SURVEY REQUEST\"")
                print(f"CLIENT ({name}): SENDING DATE SURVEY RESPONSE")
                await sock.asend(get_current_date().encode())       
                max_survey -= 1 
        
    return await curio.spawn(send_survey_eternally)


async def main():
    with pynng.Surveyor0() as surveyor:
        n0 = await server(surveyor)
        
        async with curio.TaskGroup(wait=all) as g:
            await g.spawn(client, "client0", 3)
            await g.spawn(client, "client1", 3)
            await g.spawn(client, "client2", 4)

        await n0.join()


if __name__ == "__main__":
    try:
        curio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass
