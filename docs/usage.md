# Usage

DetectMateService provides a command-line interface (CLI) `detectmate` to manage the service.

## Quick start your first Service

To run a component with default settings only, you can use this command:
```bash
detectmate start
```

You should see output like:

```
[2025-10-21 10:30:00] INFO core.abc123: Manager listening on ipc:///tmp/detectmate.cmd.ipc
[2025-10-21 10:30:00] INFO core.abc123: engine started
[2025-10-21 10:30:00] INFO core.abc123: setup_io: ready to process messages
```

## Create service settings

To run the service with custom variables, we can define settings. For example, create a file named `settings.yaml`:

```yaml
component_name: my-first-service
component_type: core  # or use a library component like "detectors.RandomDetector"
log_level: INFO
log_dir: ./logs
manager_addr: ipc:///tmp/detectmate.cmd.ipc
engine_addr: ipc:///tmp/detectmate.engine.ipc
```

## Start the service with settings

To start the service, use the `start` command. You can optionally specify a settings file and a component configuration file.

```bash
detectmate start --settings settings.yaml --config config.yaml
```

- `--settings`: Path to the service settings YAML file.
- `--config`: Path to the component configuration YAML file.

## Checking status

To check the status of a running service run:

```bash
detectmate status --settings settings.yaml
```

The `--settings` argument is required to know where to contact the service manager (via `manager_addr`).

Output:

```json
{
  "status": {
    "component_type": "core",
    "component_id": "abc123...",
    "running": true
  },
  "settings": {
    "component_name": "my-first-service",
    "log_level": "INFO",
    ...
  },
  "configs": {}
}
```

## Reconfiguring

You can update the component configuration of a running service without restarting it:

```bash
detectmate reconfigure --settings settings.yaml --config new_config.yaml
```

Add `--persist` to save the new configuration to the original config file (if supported).

```bash
detectmate reconfigure --settings settings.yaml --config new_config.yaml --persist
```

## Stopping the service

To stop the service:

```bash
detectmate stop --settings settings.yaml
```
