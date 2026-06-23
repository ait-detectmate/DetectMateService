# Configuration

DetectMateService can be configured using a YAML settings file, environment variables, or CLI flags. The precedence order is:

**CLI flags > environment variables > YAML file**

## Service settings

These settings control the service infrastructure.

| Setting                       | Env Variable                             | Default                            | Description                                                                                               |
| :---------------------------- |:-----------------------------------------|:-----------------------------------|:----------------------------------------------------------------------------------------------------------|
| `component_name`              | `DETECTMATE_COMPONENT_NAME`              | `None`                             | A human-readable name for the service instance.                                                           |
| `component_id`                | `DETECTMATE_COMPONENT_ID`                | `None` (computed)                  | Unique identifier for the component; computed automatically if not provided.                              |
| `component_type`              | `DETECTMATE_COMPONENT_TYPE`              | `core`                             | Python import path for the component class (e.g., `detectors.MyDetector`).                                |
| `component_config_class`      | `DETECTMATE_COMPONENT_CONFIG_CLASS`      | `None`                             | Python import path of the configuration class used by the component (e.g., `detectors.MyDetectorConfig`). |
| `log_level`                   | `DETECTMATE_LOG_LEVEL`                   | `INFO`                             | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                                      |
| `log_dir`                     | `DETECTMATE_LOG_DIR`                     | `./logs`                           | Directory for log files.                                                                                  |
| `log_to_console`              | `DETECTMATE_LOG_TO_CONSOLE`              | `true`                             | Whether logs are written to stdout/stderr.                                                                |
| `log_to_file`                 | `DETECTMATE_LOG_TO_FILE`                 | `true`                             | Whether logs are written to files in `log_dir`.                                                           |
| `http_host`                | `DETECTMATE_HTTP_HOST`                   | `127.0.0.1`                        | Host address for the HTTP server.                                                                         
| `http_port`                | `DETECTMATE_HTTP_PORT`                   | `8000`                             | Port for the HTTP server.                                                                                 |
| `manager_recv_timeout`        | `DETECTMATE_MANAGER_RECV_TIMEOUT`        | `100`                              | Receive timeout (ms) for the manager command channel.                                                     |
| `manager_thread_join_timeout` | `DETECTMATE_MANAGER_THREAD_JOIN_TIMEOUT` | `1.0`                              | Timeout (s) when waiting for the manager thread to stop.                                                  |
| `engine_addr`                 | `DETECTMATE_ENGINE_ADDR`                 | `ipc:///tmp/detectmate.engine.ipc` | Address for data processing (PAIR0/1).                                                                    |
| `engine_autostart`            | `DETECTMATE_ENGINE_AUTOSTART`            | `true`                             | Whether the engine starts automatically on launch. Can also be overridden at runtime with `--no-autostart`. |
| `engine_recv_timeout`         | `DETECTMATE_ENGINE_RECV_TIMEOUT`         | `100`                              | Receive timeout (ms) for the engine channel.                                                              |
| `engine_retry_count`         | `DETECTMATE_ENGINE_RETRY_COUNT`          | `10`                               | Retry count for resending messages when TryAgain exception occurs.                                        |
| `engine_buffer_size`         | `DETECTMATE_ENGINE_BUFFER_SIZE`          | `100`                              | Buffer size for the number of sent and received messages in NNG.                                          |
| `out_addr`                    | `DETECTMATE_OUT_ADDR`                    | `[]`                               | List of output addresses (strongly typed NNG URLs).                                                       |
| `out_dial_timeout`            | `DETECTMATE_OUT_DIAL_TIMEOUT`            | `1000`                             | Timeout (ms) for connecting to output addresses.                                                          |


### YAML files

You can provide a YAML file containing the service settings. Below is an example `settings.yaml`:

```yaml
component_name: "my-detector"
log_level: "DEBUG"
log_dir: "./logs"

# Manager Interface
http_host: 127.0.0.1
http_port: 8000

# Engine Interface (Data Channel)
engine_addr: "ipc:///tmp/detectmate.engine.ipc"
engine_autostart: true

# Output Destinations (where processed data is sent)
out_addr:
  - "tcp://127.0.0.1:5000"
  - "ipc:///tmp/output.ipc"

out_dial_timeout: 1000
```


### Environment variables

Environment variables override values in the YAML file. They are prefixed with `DETECTMATE_`.

Example:
```bash
export DETECTMATE_LOG_LEVEL=DEBUG
export DETECTMATE_COMPONENT_NAME=worker-1
detectmate start
```

## Component configuration

In addition to the service settings (which configure the *runner*), you can also pass a separate configuration file for the specific component logic (e.g., detector parameters) using the `--config` flag in the CLI. This file is specific to the implementation of the component you are running.

Component configuration controls the specific logic of the detector or parser. To support dynamic library loading, this file uses a nested structure.
The configuration must be namespaced by the component category (detectors or parsers) and the specific class name to allow the library to correctly route parameters.
Example detector_config.yaml


```yaml
detectors:                 # Category Level
  NewValueDetector:        # Class Name Level
    auto_config: false
    method_type: new_value_detector
    params:                # Implementation Specific Level
    events:
        1:
            test:
                params: {}
                variables:
                    - pos: 0
                      name: var1
                      params:
                          threshold: 0.5
                header_variables:
                    - pos: level
                      params: {}

```

You can read more about Components in the [Using a Library Component](library.md) section.


## HTTP Admin Interface

The service provides a REST API for runtime management and monitoring.

### Core Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/admin/status` | Returns the health, running state, and current effective configurations. |
| `POST` | `/admin/start` | Starts the data processing engine thread. |
| `POST` | `/admin/stop` | Stops the data processing engine thread. |
| `POST` | `/admin/reconfigure` | Updates component parameters dynamically. |
| `POST` | `/admin/shutdown` | Gracefully terminates the entire service process. |

### Persistency Endpoints

These endpoints are available when the loaded library component has persistency configured (via the `persist` block in its component config).

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/admin/persistency/status` | Returns persistency configuration, in-memory event counters, and timestamp of the last save. |
| `POST` | `/admin/persistency/save` | Forces an immediate flush of in-memory learned state to storage. |
| `POST` | `/admin/persistency/load` | Restores learned state from storage, replacing what is currently in memory. The engine must be stopped first, returns `409` if it is running. |

`/admin/persistency/save` and `/admin/persistency/status` return `404` if no library component is loaded or if `persist` is not configured in the component config. `/admin/persistency/load` additionally returns `409` if the engine is running. stop it first with `/admin/stop`. See [usage.md](usage.md#controlling-state-persistency) for `detectmate-client` equivalents.

#### `/admin/persistency/status` response

```json
{
  "path": "/state/NewValueDetector",
  "save_interval_seconds": 300,
  "events_until_save": null,
  "auto_load": false,
  "events_seen_count": 12,
  "events_with_data_count": 8,
  "events_since_save": 47,
  "last_saved_at": "2026-06-16T10:30:00+00:00"
}
```

| Field | Description |
| :--- | :--- |
| `path` | Storage path (local or remote fsspec URL) where state files are written. |
| `save_interval_seconds` | Background timer interval between automatic saves. |
| `events_until_save` | If set, a save is also triggered after this many ingested events. `null` means disabled. |
| `auto_load` | Whether the component loaded its previous state automatically on startup. |
| `events_seen_count` | Total number of distinct event types observed since the last load. |
| `events_with_data_count` | Number of event types that have extracted variable data stored. |
| `events_since_save` | Events ingested since the last successful save. |
| `last_saved_at` | UTC timestamp of the last successful save, or `null` if no save has occurred yet. |

### Training State Endpoints

These endpoints control whether the library component is actively training or configuring its model. They are available whenever a library component is loaded.

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/admin/training/state` | Returns the fit logic state from the last processed event. |
| `POST` | `/admin/training/state` | Overrides the training or configuration phase. |

Both endpoints return `404` if no library component is loaded. See [usage.md](usage.md#controlling-training-state) for `detectmate-client` equivalents.

#### Background: training vs. configuration

Each incoming event is evaluated by the component's fit logic, which decides what to do with it. There are two independent phases:

- **Configure**: the component learns the structure of the data (e.g. which event types and variables exist). Runs for a fixed number of events set via `data_use_configure` in the component config.
- **Train**: the component fits its model on the observed data. Runs for a fixed number of events set via `data_use_training`.

Both phases stop automatically after their configured event count. By default the component transitions to inference-only mode after that.

#### `POST /admin/training/state` payload

```json
{"state": "<value>"}
```

| Value | Effect |
| :--- | :--- |
| `keep_training` | Force training **on** indefinitely, ignoring the event count limit. |
| `stop_training` | Force training **off** immediately, ignoring the event count limit. |
| `keep_configuring` | Force the configure phase **on** indefinitely. |
| `stop_configuring` | Force the configure phase **off** immediately. |

Any other value is rejected with `422 Unprocessable Entity`.

#### `GET /admin/training/state` response

```json
{"state": "Training."}
```

The `state` field reflects what the component did with the most recently processed event:

| Value | Meaning |
| :--- | :--- |
| `"Training."` | Last event was used for model training. |
| `"Configuring"` | Last event was used for the configure phase. |
| `"Default"` | Neither,  the component is in inference-only mode. |

### Persistency component configuration

Persistency for detector components is enabled through the `persist` block in the component configuration file. When present, the component automatically saves its learned state to disk on a configurable schedule.

```yaml
detectors:
  NewValueDetector:
    method_type: new_value_detector
    persist:
      path: ./state          # Directory to store state files (supports fsspec URLs)
      interval_seconds: 300  # Save every 5 minutes (default)
      events_until_save: 1000  # Also save after every 1000 ingested events (optional)
      auto_load: true        # Restore previous state on startup (default: false)
      storage_options: {}    # Extra options passed to fsspec (e.g. S3 credentials)
```

| Field | Default | Description |
| :--- | :--- | :--- |
| `path` | `./state` | Where to write state files. Accepts any fsspec-compatible URL (`s3://`, `gs://`, local path, etc.). The component name is appended automatically. |
| `interval_seconds` | `300` | Seconds between background saves. |
| `events_until_save` | `null` | If set, trigger an additional save after this many events. Combines with the timer. |
| `auto_load` | `false` | If `true`, the component restores its previous state from `path` when it starts. |
| `storage_options` | `{}` | Passed directly to fsspec (e.g. AWS credentials, GCS project, etc.). |
