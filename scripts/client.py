import pynng
import sys


def send_message(msg: str) -> None:
    address = "ipc:///tmp/sender.engine.ipc"
    with pynng.Pair0() as sock:
        try:
            sock.dial(address, block=True)
            print(f"Client: Connected to {address}")
        except Exception as e:
            print(f"Client: Failed to connect to {address}: {e}")
            sys.exit(1)

        print(f"Client: Sending '{msg}'...")
        sock.send(msg.encode())
        print("Client: Sent.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = sys.argv[1]
    else:
        message = "Hello from manual 5"
    send_message(message)
