# Library Interface Contract

This document describes the interface contract between DetectMateService and DetectMateLibrary. If you're implementing custom components in the library, your classes must adhere to these interfaces.

## CoreComponent Interface

All processing components (readers, parsers, detectors) must inherit from `CoreComponent`:

```python
from detectmatelibrary.common.core import CoreComponent

class MyComponent(CoreComponent):
    def __init__(self, config=None):
        """Initialize the component.

        Args:
            config: Optional configuration dictionary or CoreConfig instance.
                    May be None if no configuration is provided.
        """
        super().__init__(config)
        # Your initialization here

    def process(self, data: bytes) -> bytes | None:
        """Process incoming data.

        Args:
            data: Raw bytes received from the upstream component.

        Returns:
            bytes: Processed data to forward to downstream components.
            None: Skip forwarding (filter out this message).
        """
        # Your processing logic here
        return processed_data
```

### Key Requirements

- **Constructor**: Must accept an optional `config` parameter (can be `dict` or `CoreConfig` instance)
- **process() method**: Must accept `bytes` and return `bytes | None`
- **Return behavior**:
  - Return `bytes` to forward output to downstream components
  - Return `None` to skip/filter the message (no output sent)

## CoreConfig Interface

Configuration classes must inherit from `CoreConfig`, which extends Pydantic's `BaseModel`:

```python
from detectmatelibrary.common.core import CoreConfig

class MyComponentConfig(CoreConfig):
    """Configuration for MyComponent."""
    threshold: float = 0.5
    window_size: int = 10
    enabled: bool = True
```

### Key Requirements

- **Pydantic BaseModel**: Must support `model_validate()` and `model_dump()` methods
- **Type hints**: All fields should have type annotations
- **Defaults**: Provide sensible defaults where appropriate

### Configuration Flow

1. Resolution: `ComponentResolver` expands the `component_type` from settings to a fully qualified path and derives the matching config class from it (see [Component Loading](#component-loading)). An explicit `component_config_class` is optional and takes precedence.
2. Service loads config from YAML file.
3. Schema identification: The service calls dynamically imports and verify the configuration class.
 - Validation: It ensures the config class is a subclass of `CoreConfig`.
4. Component Instantiation: The service uses to dynamically loads the resolved component class.
 - Validation: It ensures the component class is an instance of `CoreComponent`
5. Config from `ConfigManager` is passed to component constructor
6. The Library processes and validates the configuration internally
 - Validation: The library checks if `auto_config` is enabled. If disabled and no `params` exist, it raises an AutoConfigError.

 - Type Checking: It ensures the method_type matches the expected component type.

 - Formatting: It iterates through the params dictionary. For every parameter, it applies a specific format.

 - Keyword Cleaning: If a parameter key starts with `all_`, the library processes it and strips the prefix (e.g., all_threshold becomes threshold).

  - Flattening: The library flattens the structure by updating the top-level config dictionary with the contents of params and then deleting the now-redundant `params` key.
7. Processor Adaptation: The service wraps the `CoreComponent` in a `LibraryComponentProcessor` (an adapter) to make it compatible with the `Engine` loop.
8. At runtime, `reconfigure` command can update configs dynamically

## Component Loading

The `component_type` setting tells the service which class to load. You can use two forms: short class name or dotted path.

### Short class name

```yaml
component_type: RandomDetector
```

A value without a dot is treated as a class name. `ComponentResolver` walks every submodule of `detectmatelibrary` and takes the first one that exports a `CoreComponent` subclass with that name, expanding it to a fully qualified path (`detectmatelibrary.detectors.RandomDetector`).

Convenient for library components, but note:

- **Library only.** Classes in your own package are never found. You get `ImportError: Could not find a component named '...' anywhere under 'detectmatelibrary'. Use the full dotted path.`
- **First match wins.** If two modules export a class of the same name, resolution order determines which one you get.


### Dotted path

```yaml
component_type: detectors.random_detector.RandomDetector
```

A value containing a dot is treated as `module.ClassName` and used as written, without search. Use this form for custom components, and whenever you want real import errors instead of "not found":

- `detectors.random_detector.RandomDetector` - library component, `detectmatelibrary.` prefix is optional
- `detectmatelibrary.detectors.random_detector.RandomDetector` - fully qualified library component
- `mypackage.detectors.CustomDetector` - component from an external package

> **Note:** The resolved path becomes the `component_type` label on every Prometheus metric, and the two forms resolve to different strings. Use one form consistently across a deployment so dashboards do not split them into two series.

### Import resolution order

Both loaders accept library-relative and absolute paths.

| Loader | Resolves | Order |
|--------|----------|-------|
| `ComponentLoader` | `component_type` | 1. path as-is → 2. `detectmatelibrary.{path}` |
| `ConfigClassLoader` | `component_config_class` | 1. `detectmatelibrary.{path}` → 2. path as-is |

### Config class resolution

Once the component is resolved, `ComponentResolver` looks for `<ClassName>Config` in the **same module** and uses it as the configuration schema:`RandomDetector` → `RandomDetectorConfig`. Every component in DetectMateLibrary follows this convention, so `component_config_class` normally does not need to be set!

**Set it explicitly only when the convention does not hold:**

- the config class has a different name or lives in a different module than the component (in case of custom components)
- the service runs as `component_type: core` (no component to derive a schema from)

> **Warning:** If no `<ClassName>Config` is found and `component_config_class` is not set, the resolver falls back to `CoreConfig`. 

### Service Settings

In your service settings YAML, specify:

```yaml
component_type: detectors.MyDetector   # Component class path or class name
config_file: detector-config.yaml      # Path to component config
# Optional:
# component_config_class: mypackage.configs.MyDetectorSettings
#   Only needed if the config class is not <ComponentClass>Config
#   in the component's own module.
```

## Data Flow Schemas

Components in the processing pipeline use protobuf schemas for structured data exchange:

| Stage | Input | Output Schema |
|-------|-------|---------------|
| Reader | Raw source (file, network, etc.) | `LogSchema` |
| Parser | `LogSchema` bytes | `ParserSchema` |
| Detector | `ParserSchema` bytes | `DetectorSchema` |

Each component receives serialized protobuf bytes, deserializes them, processes the data, and serializes the output for the next stage.

## Complete Example

Here's a minimal detector component implementation:

### 1. Config Class (`detectors/random_detector.py`)

```python
from detectmatelibrary.common._config._formats import LogVariables, AllLogVariables

from detectmatelibrary.common.detector import CoreDetector, CoreDetectorConfig

from detectmatelibrary.utils.data_buffer import BufferMode

import detectmatelibrary.schemas as schemas

from typing_extensions import override
from typing import List, Any
import numpy as np


class RandomDetectorConfig(CoreDetectorConfig):
    method_type: str = "random_detector"

    events: EventsConfig | dict[str, Any] = {}


class RandomDetector(CoreDetector):
    """Detects anomalies randomly in logs, completely independent of the input
    data."""

    def __init__(
        self, name: str = "RandomDetector", config: RandomDetectorConfig = RandomDetectorConfig()
    ) -> None:
        if isinstance(config, dict):
            config = RandomDetectorConfig.from_dict(config, name)
        super().__init__(name=name, buffer_mode=BufferMode.NO_BUF, config=config)
        self.config: RandomDetectorConfig

    @override
    def train(self, input_: List[schemas.ParserSchema] | schemas.ParserSchema) -> None:  # type: ignore
        """Training is not applicable for RandomDetector."""
        return

    @override
    def detect(
        self, input_: schemas.ParserSchema, output_: schemas.DetectorSchema  # type: ignore
    ) -> bool:
        """Detect anomalies randomly in the input data."""
        overall_score = 0.0
        alerts = {}

        event_config = self.config.events[input_["EventID"]]
        if event_config is None:
            return False

        relevant_log_fields = event_config.get_all()
        for log_variable in relevant_log_fields.values():
            score = 0.0
            random = np.random.rand()
            if random > log_variable.params["threshold"]:
                score = 1.0
                # Variable has .name, Header has .pos (str)
                var_name = log_variable.name if isinstance(log_variable, Variable) else log_variable.pos
                alerts.update({var_name: str(score)})
            overall_score += score

        if overall_score > 0:
            output_["score"] = overall_score
            output_["alertsObtain"].update(alerts)
            return True

        return False
```

### 2. Service Settings (`settings.yaml`)

```yaml
component_name: random-detector
component_type: detectors.random_detector.RandomDetector
config_file: random-config.yaml
log_level: INFO
http_host: 127.0.0.1
http_port: 8000
engine_addr: ipc:///tmp/threshold.engine.ipc
```

### 3. Component Config (`random-config.yaml`)

Component configuration uses a nested structure:

```yaml
detectors:
    RandomDetector:
        method_type: random_detector
        auto_config: False
        params: {}
        events:
            1:
                test:
                    params: {}
                    variables:
                        - pos: 0
                          name: var1
                          params:
                              threshold: 0.
                    header_variables:
                        - pos: level
                          params: {}
```

This hierarchical format allows the library to correctly route parameters based on category and class name.

### 4. Run the Service

```bash
detectmate --settings settings.yaml --configs random-config.yaml
```

## Validation

The service validates components at load time:

1. **Component class**: Must be an instance of `CoreComponent` (in `ComponentLoader`)
2. **Config class**: Must be a subclass of `CoreConfig` (in `ConfigClassLoader`)

If validation fails, the service raises an error.
