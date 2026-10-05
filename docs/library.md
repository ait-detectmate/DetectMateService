> **Note**: For implementing custom library components, see the [Library Interface Contract](interfaces.md).

## Using a Library Component

The Service can be run as any component imported from the [DetectMateLibrary](https://github.com/ait-detectmate/DetectMateLibrary).
For this, ensure that the library is installed in the same activated virtual environment, where the service is installed.

> **Note:** Some library components depend on optional extras (e.g. LLM-backed
> detectors need `llm`, dataframe-based persistency backends need `dataframes`).
> If the component you want to use raises an `ImportError` mentioning a missing
> extra, install the service with the matching extra — see
> [Optional library components](installation.md#optional-library-components-extras)
> in the installation guide.

### 1. Update settings

Modify `settings.yaml` to use a library component:

```yaml
--8<-- "docs/examples/library/settings.yaml"
```

### 2. Create component configuration

Create `detector-config.yaml`. The nesting (category and class name) is the same for every
component, but the other fields depend on the component's config class and differ
per component. Check the individual component's page in the
[DetectMateLibrary documentation](https://ait-detectmate.github.io/DetectMateLibrary/latest/detectors/)
and [Component configuration](configuration.md#component-configuration):

```yaml
--8<-- "docs/examples/library/detector-config.yaml"
```

### 3. Start with configuration

```bash
detectmate --settings settings.yaml --config detector-config.yaml
```

### 4. Reconfigure at runtime

Create `new-config.yaml`:

```yaml
--8<-- "docs/examples/library/new-config.yaml"
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
--8<-- "docs/examples/library/detector_persist_config.yaml"
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

> **Warning:** `/admin/persistency/load` returns `409 Conflict` if the engine is running. Stop it first with `/admin/stop`, then load, then restart with `/admin/start`. Loading while the engine is active would corrupt in-memory state otherwise the detector could end up with a mix of old and restored data with no error to indicate something went wrong.

You can also use `detectmate-client` instead of curl — see [usage.md](usage.md#controlling-state-persistency).

#### Exporting and importing state

You can download the current learned state as a portable zip archive and restore it later. Useful for backups, moving state between environments, or seeding a new instance.

```bash
# Download the current state to a local file
curl http://127.0.0.1:8000/admin/persistency/export -o detector_state.zip

# Restore state from a previously downloaded archive
# (stop the engine first, import returns 409 if it is running)
curl -X POST http://127.0.0.1:8000/admin/stop
curl -X POST http://127.0.0.1:8000/admin/persistency/import -F "file=@detector_state.zip"
curl -X POST http://127.0.0.1:8000/admin/start
```

You can also use `detectmate-client` instead of curl:

```bash
# Download the current state to a local file
detectmate-client --url 127.0.0.1:8000 persistency-export detector_state.zip

# Restore state from a previously downloaded archive
# (stop the engine first, import returns 409 if it is running)
detectmate-client --url 127.0.0.1:8000 stop
detectmate-client --url 127.0.0.1:8000 persistency-import detector_state.zip
detectmate-client --url 127.0.0.1:8000 start
```

See [usage.md](usage.md#controlling-state-persistency) for details.

The archive contains `metadata.json` plus per-event data files. Import returns `422` if the file is not a valid zip or if `metadata.json` is missing.

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
