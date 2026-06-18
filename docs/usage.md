# Usage

DetectMateService provides a command-line interface (CLI) `detectmate` to manage the service.

## Quick start your first Service

To run a component with default settings only, you can use this command:
```bash
detectmate
```

You should see output like:

```
[2026-01-20 15:16:21,140] INFO service.cli: config file: None
[2026-01-20 15:16:21,140] INFO service.cli: config file: None
[2026-01-20 15:16:21,143] INFO core.5958cc49c05e572baa4f0acbc4b33f87: No output addresses configured, processed messages will not be forwarded
[2026-01-20 15:16:21,143] INFO core.5958cc49c05e572baa4f0acbc4b33f87: engine started
[2026-01-20 15:16:21,143] INFO core.5958cc49c05e572baa4f0acbc4b33f87: setup_io: ready to process messages
[2026-01-20 15:16:21,143] INFO core.5958cc49c05e572baa4f0acbc4b33f87: HTTP Admin active at 127.0.0.1:8000
[2026-01-20 15:16:21,143] INFO core.5958cc49c05e572baa4f0acbc4b33f87: Auto-starting engine...
INFO:     Started server process [3933168]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)

```

## Create service settings

To run the service with custom variables, we can define settings. For example, create a file named `settings.yaml`:

```yaml
component_name: my-first-service
component_type: core  # or use a library component like "detectors.RandomDetector"
log_level: INFO
log_dir: ./logs
http_host: 127.0.0.1
http_port: 8000
engine_addr: ipc:///tmp/detectmate.engine.ipc
```

## Start the service with settings

To start the service, use the `detectmate` command. You can optionally specify a settings file and a component configuration file.

```bash
detectmate --settings settings.yaml --config config.yaml
```

- `--settings`: Path to the service settings YAML file.
- `--config`: Path to the component configuration YAML file.

## Checking status

To check the status of a running service run:

```bash
detectmate-client status --url <http_host:http_port>
```

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
detectmate-client --url <http_host:http_port> reconfigure new_config.yaml
```

Add `--persist` to save the new configuration to the original config file (if supported).

```bash
detectmate --url <http_host:http_port> reconfigure new_config.yaml --persist
```

## Stopping the service

To stop the service:

```bash
detectmate stop --url <http_host:http_port>
```

## Controlling state persistency

When a component has persistency configured, you can manage its saved state at runtime.

```bash
# Show persistency config, event counters, and last save timestamp
detectmate-client --url <http_host:http_port> persistency-status

# Force an immediate save of learned state to storage
detectmate-client --url <http_host:http_port> persistency-save

# Restore learned state from storage (replaces current in-memory state)
detectmate-client --url <http_host:http_port> persistency-load
```

These commands return `404` if persistency is not configured for the loaded component. See [configuration.md](configuration.md) for how to enable persistency via the `persist` block.

## Controlling training state

By default a detector trains for a fixed number of events, then switches to inference-only mode. You can override this at runtime:

```bash
# Check what the component is currently doing
detectmate-client --url <http_host:http_port> training-get-state

# Freeze the model, stop training immediately
detectmate-client --url <http_host:http_port> training-set-state stop_training

# Resume training, eep updating past the configured event limit
detectmate-client --url <http_host:http_port> training-set-state keep_training

# Force the configure phase on or off
detectmate-client --url <http_host:http_port> training-set-state keep_configuring
detectmate-client --url <http_host:http_port> training-set-state stop_configuring
```

Valid values for `training-set-state` are `keep_training`, `stop_training`, `keep_configuring`, and `stop_configuring`. Any other value is rejected before the request is sent.
