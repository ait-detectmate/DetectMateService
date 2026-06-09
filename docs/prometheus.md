# Monitoring with Prometheus

Every DetectMate service exposes a Prometheus-compatible metrics endpoint on its HTTP server. Prometheus can scrape this endpoint to collect operational metrics, and tools like Grafana can visualize them.

## Metrics endpoint

The metrics endpoint is available at:

```
http://<http_host>:<http_port>/metrics
```

With default settings this is `http://127.0.0.1:8000/metrics`. You can fetch it directly with curl:

```bash
curl http://127.0.0.1:8000/metrics
```

Or use the DetectMate client CLI:

```bash
detectmate-client --url http://127.0.0.1:8000 metrics
```

## Available metrics

All metrics are labeled with `component_type` and `component_id`, so a single Prometheus instance can distinguish between multiple DetectMate services.

| Metric | Type | Description |
| :----- | :--- | :---------- |
| `engine_running` | Enum (`running`, `stopped`) | Current state of the processing engine |
| `engine_starts_total` | Counter | Number of times the engine has been started |
| `processing_duration_seconds` | Histogram | Time spent processing each message, in seconds |
| `processing_errors_total` | Counter | Number of exceptions raised during processing |
| `data_read_bytes_total` | Counter | Total bytes read from input interfaces |
| `data_read_lines_total` | Counter | Total lines read from input interfaces |
| `data_processed_bytes_total` | Counter | Total bytes processed by the component |
| `data_processed_lines_total` | Counter | Total lines processed by the component |
| `data_written_bytes_total` | Counter | Total bytes written to output interfaces |
| `data_written_lines_total` | Counter | Total lines written to output interfaces |
| `data_dropped_bytes_total` | Counter | Total bytes dropped due to disconnected or slow downstream peers |
| `data_dropped_lines_total` | Counter | Total lines dropped due to disconnected or slow downstream peers |

The `processing_duration_seconds` histogram uses the following buckets: 1 ms, 5 ms, 10 ms, 25 ms, 50 ms, 100 ms, 250 ms, 500 ms, 1 s, 2.5 s, 5 s, 10 s.

!!! note "Counting with multiple output interfaces"
    When multiple output addresses are configured, `data_written_bytes_total` and `data_written_lines_total` are incremented **once per message** as long as at least one output send succeeded. `data_dropped_bytes_total` and `data_dropped_lines_total` are incremented **once per failing output interface**, so a single message can contribute to the dropped counter multiple times if several outputs are unavailable simultaneously.

## Connecting a standalone Prometheus

If you run DetectMate outside of Docker Compose, add a scrape job to your `prometheus.yml`:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'detectmate'
    static_configs:
      - targets:
          - '127.0.0.1:8000'
```

If you run multiple services, list each one under `targets`:

```yaml
scrape_configs:
  - job_name: 'detectmate'
    static_configs:
      - targets:
          - '127.0.0.1:8001'  # parser
          - '127.0.0.1:8002'  # detector
```

## Docker Compose setup

The DetectMate repository ships a ready-to-use Docker Compose configuration that includes Prometheus and Grafana. The Prometheus configuration file at `container/prometheus.yml` is pre-configured to scrape the `parser` and `detector` services:

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['parser:8000', 'detector:8000']
```

Prometheus is accessible at `http://localhost:9090` after starting the stack with:

```bash
docker compose up
```

See the [Docker Compose reference](docker-compose.md) for details on the full stack setup.

## Visualizing metrics with Grafana

The Docker Compose stack includes a Grafana instance pre-configured with Prometheus as a datasource. Access it at `http://localhost:3000` (default credentials: `admin` / `admin`).

To explore DetectMate metrics, open "Drilldown" and select "Metrics". Filter by the `detectmate` job or search for any of the metric names listed above.

!!! note
    If you connect your own Grafana to a standalone Prometheus, add a Prometheus datasource pointing to `http://<prometheus-host>:9090`.
