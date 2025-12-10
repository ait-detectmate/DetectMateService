import pynng
import sys
import time

def send_message(msg):
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
        # Wait a bit for potential reply if any, though in this architecture 
        # the engine might not reply on PAIR if it forwards. 
        # But let's see if we get anything back or just exit.
        print("Client: Sent.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        message = sys.argv[1]
    else:
        message = "Hello from manual client"
    send_message(message)
