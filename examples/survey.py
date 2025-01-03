"""
The surveyor pattern is used to send a timed survey out,
responses are individually returned until the survey has expired.
This pattern is useful for service discovery and voting algorithms.
"""

import datetime
import pynng
import trio


DATE = "DATE"
address = "ipc:///tmp/survey.ipc"


def get_current_date():
    return str(datetime.datetime.now())


async def server(sock, max_survey_request=10):
    while max_survey_request:
        print(f"SERVER: SENDING DATE SURVEY REQUEST")
        await sock.asend(DATE.encode())
        while True:
            try:
                msg = await sock.arecv_msg()
                print(f'SERVER: RECEIVED "{msg.bytes.decode()}" SURVEY RESPONSE')
            except pynng.Timeout:
                break
        print("SERVER: SURVEY COMPLETE")
        max_survey_request -= 1


async def client(name, max_survey=3):
    with pynng.Respondent0() as sock:
        sock.dial(address)
        while max_survey:
            await sock.arecv_msg()
            print(f'CLIENT ({name}): RECEIVED SURVEY REQUEST"')
            print(f"CLIENT ({name}): SENDING DATE SURVEY RESPONSE")
            await sock.asend(get_current_date().encode())
            max_survey -= 1


async def main():
    with pynng.Surveyor0(listen=address) as surveyor:
        async with trio.open_nursery() as nursery:
            nursery.start_soon(server, surveyor)
            nursery.start_soon(client, "client0", 3)
            nursery.start_soon(client, "client1", 3)
            nursery.start_soon(client, "client2", 4)


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        # that's the way the program *should* end
        pass
