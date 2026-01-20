# Running the Docker Pipeline

There is a containerized demonstration of the DetectMate log analysis pipeline. The demo runs three services (reader, parser,
detector) that process audit logs to detect anomalies, with a test script that feeds log lines through the complete
pipeline and reports detected anomalies. Each component runs in its own Docker container and the components communicate via TCP.

This document explains how to run the example pipeline using Docker, located in the `demo` folder.


## Components

The pipeline consists of the following services defined in `demo/docker-compose.yml`:

1.  **Reader (`detectmate_reader`)**:
    *   reads log lines from a source file (`demo/data/audit.log`)
    *   uses `demo/config/reader_config.yaml`
    *   listens on internal port **8001**

2.  **Parser (`detectmate_parser`)**:
    *   receives raw log data, parses it into a structured format
    *   uses `demo/config/parser_config.yaml`
    *   listens on internal port **8011**
    *   depends on the Reader

3.  **Detector (`detectmate_detector`)**:
    *   analyzes structured logs to detect anomalies
    *   uses `demo/config/detector_config.yaml`
    *   listens on internal port **8021**
    *   depends on the Parser

4.  **Demo Driver (`detectmate_demo`)**:
    *   Acts as the orchestrator/client. It executes the `demo/manual_demo_run_tcp.py` script. It does the following:
        1. count lines in the audit log
        2. for each line, it sends a request to the **Reader** to get a log line
        3. forwards the log line to the **Parser** for processing
        4. forwards the parsed data to the **Detector** for analysis
        5. prints any detected anomalies to the console


## How to Run

Prerequisites: **Docker** and **Docker Compose** installed.

**Terminal 1** (keep running to see service logs):
```bash
cd demo
docker compose up reader parser detector
```

**Terminal 2** (run after services are up):
```bash
cd demo
docker compose up demo
```


## Directory Structure

*   `demo/Dockerfile`: The Docker definition used by all services.
*   `demo/docker-compose.yml`: Defines the multi-container application.
*   `demo/config/`: Contains YAML configuration files for Reader, Parser, and Detector.
*   `demo/data/`: Contains sample data (e.g., `audit.log`) used by the Reader.
*   `demo/manual_demo_run_tcp.py`: The Python script running inside the `demo` container that drives the flow.
