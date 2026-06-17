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
