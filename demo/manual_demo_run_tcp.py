import pynng
from detectmatelibrary.helper.from_to import From
from detectmatelibrary.parsers.dummy_parser import DummyParser


LOG_PATH = "/app/demo/data/audit.log"
DETECTOR_OUT = "/app/demo/data/detector_out.json"


def process_logs() -> None:
    """Read the audit log and send each line through reader, parser, and
    detector over TCP."""
    with open(LOG_PATH, "r") as f:
        total = sum(1 for _ in f)
    print(f"Processing {total} log lines...")
    parser = DummyParser()
    gen = From.log(parser, LOG_PATH, do_process=False)
    i = 1
    while True:
        try:
            # Step 1: Reader
            line = next(gen)
        except StopIteration:
            break
        print(f"\n--- Processing line {i}/{total} ---")
        i += 1
        try:
            # Step 2: Parser
            with pynng.Pair0(dial="tcp://parser:8011") as parser:
                parser.send(line.serialize())
                log_response2 = parser.recv()
            # Step 3: Detector
            with pynng.Pair0(dial="tcp://detector:8021", recv_timeout=10) as detector:
                detector.send(log_response2)
                try:
                    log_response3 = detector.recv()
                    print(f"Anomaly detected: {log_response3}")
                except pynng.Timeout:
                    # No anomaly, just continue
                    pass
        except Exception as e:
            print(f"Error on line {i}: {e}")


if __name__ == "__main__":
    process_logs()
