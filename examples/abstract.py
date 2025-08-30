#!/usr/bin/env python3
"""
Example demonstrating the use of abstract sockets in pynng.

Abstract sockets are a Linux-specific feature that allows for socket communication
without creating files in the filesystem. They are identified by names in an
abstract namespace.

To run this example (on Linux only):

    # Terminal 1
    python abstract.py node0 abstract://my_test_socket

    # Terminal 2
    python abstract.py node1 abstract://my_test_socket

You can also test with special characters:

    # Terminal 1
    python abstract.py node0 "abstract://test%00socket"

    # Terminal 2
    python abstract.py node1 "abstract://test%00socket"

Or test auto-bind functionality:

    # Terminal 1
    python abstract.py node0 abstract://

    # Terminal 2
    python abstract.py node1 abstract://
"""

import sys
import time
import platform
import pynng


def usage():
    """Print usage message and exit."""
    print("Usage: {} node0|node1 URL".format(sys.argv[0]))
    print("")
    print("Example URLs:")
    print("  abstract://my_test_socket")
    print("  abstract://test%00socket  (with NUL byte)")
    print("  abstract://               (auto-bind)")
    print("")
    print(
        "Note: Abstract sockets are Linux-specific and will not work on other platforms."
    )
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        usage()

    node = sys.argv[1]
    if node not in ("node0", "node1"):
        usage()

    url = sys.argv[2]

    # Check if we're on Linux
    if platform.system() != "Linux":
        print("Error: Abstract sockets are only supported on Linux.")
        print(f"Current platform: {platform.system()}")
        sys.exit(1)

    # Check if URL starts with abstract://
    if not url.startswith("abstract://"):
        print("Error: URL must start with 'abstract://'")
        usage()

    print(f"Starting {node} with URL: {url}")

    try:
        with pynng.Pair0(recv_timeout=100, send_timeout=100) as sock:
            if node == "node0":
                # Node 0 listens
                print(f"Listening on {url}")
                listener = sock.listen(url)

                # Print information about the listener
                local_addr = listener.local_address
                print(f"Local address: {local_addr}")
                print(f"Address family: {local_addr.family_as_str}")
                print(f"Address name: {local_addr.name}")

                # Wait for connections and messages
                while True:
                    try:
                        msg = sock.recv()
                        print(f"Received message: {msg.decode()}")
                    except pynng.Timeout:
                        pass

                    # Send a message periodically
                    try:
                        sock.send(f"Hello from {node} at {time.time()}".encode())
                    except pynng.Timeout:
                        pass

                    time.sleep(0.5)

            else:
                # Node 1 dials
                print(f"Dialing {url}")
                dialer = sock.dial(url)

                # Print information about the dialer
                try:
                    local_addr = dialer.local_address
                    print(f"Local address: {local_addr}")
                    print(f"Address family: {local_addr.family_as_str}")
                except pynng.NotSupported:
                    print(
                        "Local address not supported for dialer with abstract sockets"
                    )

                # Wait for connections and messages
                while True:
                    try:
                        msg = sock.recv()
                        print(f"Received message: {msg.decode()}")
                    except pynng.Timeout:
                        pass

                    # Send a message periodically
                    try:
                        sock.send(f"Hello from {node} at {time.time()}".encode())
                    except pynng.Timeout:
                        pass

                    time.sleep(0.5)

    except pynng.NNGException as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)


if __name__ == "__main__":
    main()
