# Configuration

DetectMateService can be configured using a YAML settings file or environment variables. Environment variables take precedence over the YAML file.

## Service settings

These settings control the service infrastructure.

| Setting                       | Env Variable                             | Default                            | Description                                                                                               |
| :---------------------------- | :--------------------------------------- | :--------------------------------- |:----------------------------------------------------------------------------------------------------------|
| `component_name`              | `DETECTMATE_COMPONENT_NAME`              | `None`                             | A human-readable name for the service instance.                                                           |
| `component_id`                | `DETECTMATE_COMPONENT_ID`                | `None` (computed)                  | Unique identifier for the component; computed automatically if not provided.                              |
| `component_type`              | `DETECTMATE_COMPONENT_TYPE`              | `core`                             | Python import path for the component class (e.g., `detectors.MyDetector`).                                |
| `component_config_class`      | `DETECTMATE_COMPONENT_CONFIG_CLASS`      | `None`                             | Python import path of the configuration class used by the component (e.g., `detectors.MyDetectorConfig`). |
| `log_level`                   | `DETECTMATE_LOG_LEVEL`                   | `INFO`                             | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).                                                      |
| `log_dir`                     | `DETECTMATE_LOG_DIR`                     | `./logs`                           | Directory for log files.                                                                                  |
| `log_to_console`              | `DETECTMATE_LOG_TO_CONSOLE`              | `true`                             | Whether logs are written to stdout/stderr.                                                                |
| `log_to_file`                 | `DETECTMATE_LOG_TO_FILE`                 | `true`                             | Whether logs are written to files in `log_dir`.                                                           |
| `manager_addr`                | `DETECTMATE_MANAGER_ADDR`                | `ipc:///tmp/detectmate.cmd.ipc`    | Address for management commands (REQ/REP).                                                                |
| `manager_recv_timeout`        | `DETECTMATE_MANAGER_RECV_TIMEOUT`        | `100`                              | Receive timeout (ms) for the manager command channel.                                                     |
| `manager_thread_join_timeout` | `DETECTMATE_MANAGER_THREAD_JOIN_TIMEOUT` | `1.0`                              | Timeout (s) when waiting for the manager thread to stop.                                                  |
| `engine_addr`                 | `DETECTMATE_ENGINE_ADDR`                 | `ipc:///tmp/detectmate.engine.ipc` | Address for data processing (PAIR0/1).                                                                    |
| `engine_autostart`            | `DETECTMATE_ENGINE_AUTOSTART`            | `true`                             | Whether the engine channel is started automatically.                                                      |
| `engine_recv_timeout`         | `DETECTMATE_ENGINE_RECV_TIMEOUT`         | `100`                              | Receive timeout (ms) for the engine channel.                                                              |
| `out_addr`                    | `DETECTMATE_OUT_ADDR`                    | `[]`                               | List of output addresses (strongly typed NNG URLs).                                                       |
| `out_dial_timeout`            | `DETECTMATE_OUT_DIAL_TIMEOUT`            | `1000`                             | Timeout (ms) for connecting to output addresses.                                                          |


### YAML files

You can provide a YAML file containing the service settings. Below is an example `settings.yaml`:

```yaml
component_name: "my-detector"
log_level: "DEBUG"
log_dir: "./logs"

# Manager Interface (Command Channel)
manager_addr: "ipc:///tmp/detectmate.cmd.ipc"

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



```yaml
# detector-config.yaml
threshold: 0.85
sensitivity: high
enabled: true
```

You can read more about Components in the [Using a Library Component](library.md) section.
