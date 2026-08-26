# Getting Started

DetectMate enables the creation of log analysis pipelines to analyze log data streams and detect violations or anomalies. It can be run from the console or embedded in Python programs as a library. Designed to operate analyses with limited resources and the lowest possible permissions, DetectMate is suitable for use on production servers. In practice, log analysis involves distinct steps that are central to its operation.

Logfile analysis consists of two main steps: first, parsing log lines, and second, detecting anomalies within those parsed lines. In modern systems, multiple applications process logs at various stages, creating a flow from raw log ingestion to final anomaly detection, and most likely even across different network nodes. This requires a highly configurable system to maintain the flexibility to create suitable log pipelines. DetectMate, therefore, uses a microservice architecture that allows connecting all components together as needed.

Logfile ingestion is handled by Fluentd. It supports reading from various systems and can convert the data to a specific format before sending it to any other target. In our example, it reads lines from a file and sends them to the DetectMate parser. The parser processes the data and forwards them to the detector. If the detector finds an anomaly, it will send it to another Fluentd process that can communicate with various targets, such as Elasticsearch, Kafka, or a log file. To make configuring such a pipeline straightforward, the DetectmateService repository ships a boilerplate Docker Compose file. This tutorial will use the Docker Compose file so that we can focus on the anomaly detection only.

## The Objective

In this tutorial, we will set up a log data analysis pipeline that reads nginx access logs. We will then train the detector on various paths in the HTTP requests. Finally, we will generate anomalies by sending HTTP requests to different paths of the trained model.

For easy reproduction of the getting started example, we created the scripts/getting_started.sh [getting_started.sh](../scripts/getting_started.sh) script.
This script guides the user through each of the following steps:
- Check OS release (lsb_release -a).
- Install NGINX and create first log line (sudo apt update && sudo apt install nginx -y && curl http://localhost).
- Install Docker, if not already installed (https://docs.docker.com/engine/install/ubuntu/).
- Clone DetectMateService into /tmp/DetectMateService (cd /tmp && git clone https://github.com/ait-detectmate/DetectMateService.git && cd DetectMateService).
- Deploy default pipeline for testing (sudo docker compose up -d, sudo docker compose ps, sudo docker compose down -v).
- Mount previously created access.log into the [docker-compose.yml](../docker-compose.yml).
- Create DetectMate configs and start docker compose (configs are already pre-defined, sudo docker compose up -d, sudo docker compose ps, sudo docker compose down -v).
- Generate two log lines for training and one log line to produce an anomaly (curl http://localhost/hello, curl http://localhost/world, curl http://localhost/foobar (anomaly)).
- Provide first look at the Grafana UI (open http://localhost:3000 → admin/admin → Drilldown → Metrics → Dashboards.

Use `./scripts/getting_started.sh` to get started with DetectMate.

Using `-y` you can skip all continue questions.

This script is tested for Ubuntu 24.04, however, it should also work on newer versions.
Use at your own risk.

Example outputs for an unsupported system based on Ubuntu 24.04 (Linux Mint 22.3) can be found [here](examples/getting_started/getting-started-output.txt).
