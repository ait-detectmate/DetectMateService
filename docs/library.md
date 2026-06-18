> **Note**: For implementing custom library components, see the [Library Interface Contract](interfaces.md).

## Using a Library Component

The Service can be run as any component imported from the [DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary).
For this, ensure that the library is installed in the same activated virtual environment, where the service is installed.

### 1. Update settings

Modify `settings.yaml` to use a library component:

```yaml
component_name: new_value_detector
component_type: detectors.NewValueDetector
component_config_class: detectors.NewValueDetectorConfig
config_file: detector-config.yaml
log_level: INFO
manager_addr: ipc:///tmp/detectmate.cmd.ipc
engine_addr: ipc:///tmp/detectmate.engine.ipc
```

### 2. Create component configuration

Create `detector-config.yaml`:

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
```

### 3. Start with configuration

```bash
detectmate --settings settings.yaml --config detector-config.yaml
```

### 4. Reconfigure at runtime

Create `new-config.yaml`:

```yaml
detectors:
  NewValueDetector:
    auto_config: false
    method_type: new_value_detector
    params:
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

The service supports dynamic reconfiguration with two modes:

#### 1. In-memory update (default)
Changes are applied to the running service but not saved to disk. The changes will be lost when the service restarts.

```bash
detectmate-client --url 127.0.0.1:8000 reconfigure path/to/new-config.yaml
```

#### 2. Persistent update (with --persist flag)
Changes are applied to the running service AND saved to the original parameter file. The changes persist across service restarts.

```bash
detectmate-client --url 127.0.0.1:8000 reconfigure path/to/new-config.yaml --persist
```

**Note:** The `--persist` flag will overwrite the original parameter file specified in your service configuration with the new values.

### 5. Enable state persistency

Detectors accumulate learned state (observed values, variable distributions, etc.) during training. You can configure the service to automatically save this state to disk and restore it across restarts.

Add a `persist` block to your component config:

```yaml
detectors:
  NewValueDetector:
    method_type: new_value_detector
    persist:
      path: ./state      # Where to store state files
      interval_seconds: 300  # Auto-save every 5 minutes
      auto_load: true    # Restore previous state on startup
```

The state is written under `{path}/{ComponentName}/` as a `metadata.json` index plus per-event data files (`.msgpack` for tracker backends, `.parquet` for dataframe backends).

#### Controlling persistency at runtime

Once persistency is configured, three admin endpoints become available:

```bash
# Check current state: events seen, events since last save, last save timestamp
curl http://127.0.0.1:8000/admin/persistency/status

# Force an immediate save (e.g. before a planned maintenance window)
curl -X POST http://127.0.0.1:8000/admin/persistency/save

# Restore state from disk (e.g. after rolling back to a previous snapshot)
curl -X POST http://127.0.0.1:8000/admin/persistency/load
```

> **Warning:** `/admin/persistency/load` replaces the current in-memory state immediately. If the engine is actively processing data, consider stopping it first with `/admin/stop`, loading, then restarting with `/admin/start`.

You can also use `detectmate-client` instead of curl — see [usage.md](usage.md#controlling-state-persistency).

### 6. Control training at runtime

Detectors go through two phases as they process events: a **configure** phase (learning data structure) and a **train** phase (fitting the model). Both run automatically for a fixed number of events configured via `data_use_configure` and `data_use_training`. After those limits are reached, the component switches to inference-only mode.

You can override this behaviour at any time using the training state endpoints:

```bash
# Check what the component is currently doing
curl http://127.0.0.1:8000/admin/training/state
# → {"state": "Training."}  |  "Configuring"  |  "Default"

# Freeze the model — stop updating it with new events
curl -X POST http://127.0.0.1:8000/admin/training/state \
  -H "Content-Type: application/json" \
  -d '{"state": "stop_training"}'

# Resume training — keep updating even past the configured event limit
curl -X POST http://127.0.0.1:8000/admin/training/state \
  -H "Content-Type: application/json" \
  -d '{"state": "keep_training"}'

# Similarly for the configure phase
curl -X POST http://127.0.0.1:8000/admin/training/state \
  -H "Content-Type: application/json" \
  -d '{"state": "stop_configuring"}'

curl -X POST http://127.0.0.1:8000/admin/training/state \
  -H "Content-Type: application/json" \
  -d '{"state": "keep_configuring"}'
```

The four valid state values are `keep_training`, `stop_training`, `keep_configuring`, and `stop_configuring`. Any other value is rejected with `422`.

You can also use `detectmate-client` instead of curl — see [usage.md](usage.md#controlling-training-state).
