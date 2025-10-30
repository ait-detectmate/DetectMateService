import pynng


LOG_PATH = "data/audit.log"


def process_logs() -> None:
    """Read the audit log and send each line through reader, parser, and
    detector engines."""
    with open(LOG_PATH, "r") as f:
        total = sum(1 for _ in f)
    print(f"Processing {total} log lines...")

    for i in range(total):
        print(f"\n--- Processing line {i + 1}/{total} ---")

        try:
            # Step 1: Reader
            with pynng.Pair0(dial="ipc:///tmp/test_reader_engine.ipc") as reader:
                reader.send(b"sdf")
                log_response1 = reader.recv()

            # Step 2: Parser
            with pynng.Pair0(dial="ipc:///tmp/test_parser_engine.ipc") as parser:
                parser.send(log_response1)
                log_response2 = parser.recv()

            # Step 3: Detector
            with pynng.Pair0(
                dial="ipc:///tmp/test_nvd_engine.ipc",
                recv_timeout=10,
            ) as detector:
                detector.send(log_response2)
                try:
                    log_response3 = detector.recv()
                    print(f"Anomaly detected: {log_response3}")
                except pynng.Timeout:
                    # No anomaly, just continue
                    pass

        except Exception as e:
            print(f"Error on line {i + 1}: {e}")


if __name__ == "__main__":
    process_logs()
