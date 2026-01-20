## Using a Library Component

The Service can be run as any component imported from the [DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary).
For this, ensure that the library is installed in the same activated virtual environment, where the service is installed.

### 1. Update settings

Modify `settings.yaml` to use a library component:

```yaml
component_name: random-detector
component_type: detectors.RandomDetector
component_config_class: detectors.RandomDetectorConfig
config_file: detector-config.yaml
log_level: INFO
manager_addr: ipc:///tmp/detectmate.cmd.ipc
engine_addr: ipc:///tmp/detectmate.engine.ipc
```

### 2. Create component configuration

Create `detector-config.yaml`:

```yaml
threshold: 0.75
window_size: 10
enabled: true
```

### 3. Start with configuration

```bash
detectmate start --settings settings.yaml --config detector-config.yaml
```

### 4. Reconfigure at runtime

Create `new-config.yaml`:

```yaml
threshold: 0.85
window_size: 15
enabled: true
```

The service supports dynamic reconfiguration with two modes:

#### 1. In-memory update (default)
Changes are applied to the running service but not saved to disk. The changes will be lost when the service restarts.

```bash
detectmate reconfigure --settings settings.yaml --config new-config.yaml
```

#### 2. Persistent update (with --persist flag)
Changes are applied to the running service AND saved to the original parameter file. The changes persist across service restarts.

```bash
detectmate reconfigure --settings settings.yaml --config new-config.yaml --persist
```

**Note:** The `--persist` flag will overwrite the original parameter file specified in your service configuration with the new values from the `--params` file.
