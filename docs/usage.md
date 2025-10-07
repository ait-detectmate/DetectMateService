# Usage

## Parameter Management

The service supports dynamic parameter reconfiguration with two modes:

### 1. In-Memory Update (default)
Changes are applied to the running service but not saved to disk. The changes will be lost when the service restarts.

```bash
detectmate reconfigure --settings service_config.yaml --params new_params.yaml
```

### 2. Persistent Update (with --persist flag)
Changes are applied to the running service AND saved to the original parameter file. The changes persist across service restarts.

```bash
detectmate reconfigure --settings service_config.yaml --params new_params.yaml --persist
```

**Note:** The `--persist` flag will overwrite the original parameter file specified in your service configuration with the new values from the `--params` file.

## Example Parameter File
```yaml
threshold: 0.7
window_size: 15
enabled: true
```
