# Library Import Points

This document provides an overview of where DetectMateService imports from DetectMateLibrary and how those imports are used. For implementation details of the library classes, refer to the DetectMateLibrary documentation.

## Summary of Imports

| Import | Source Module | Used In | Purpose |
|--------|---------------|---------|---------|
| `CoreComponent` | `detectmatelibrary.common.core` | `core.py`, `component_loader.py` | Base class for all processing components |
| `CoreConfig` | `detectmatelibrary.common.core` | `core.py`, `config_loader.py`, `config_manager.py` | Base class for configuration schemas |
| `LogSchema` | `detectmatelibrary.schemas` | Integration tests | Parser input format |
| `ParserSchema` | `detectmatelibrary.schemas` | Integration tests | Parser output format |
| `DetectorSchema` | `detectmatelibrary.schemas` | Integration tests | Detector output format |

## CoreComponent

**Import location:** `src/service/core.py`, `src/service/features/component_loader.py`

```python
from detectmatelibrary.common.core import CoreComponent
```

### Usage Points

#### 1. Component Loading (`component_loader.py`)

The `ComponentLoader` dynamically imports component classes and validates they inherit from `CoreComponent`:

- **Instantiation**: Components are instantiated with an optional config parameter
- **Type checking**: `isinstance(instance, CoreComponent)` validates the loaded class

```python
instance = component_class(config=config)
if not isinstance(instance, CoreComponent):
    raise TypeError(...)
```

#### 2. Message Processing (`core.py`)

`Service` is itself the engine's processor: the `Engine` loop calls `Service.process()` for each incoming message, which delegates to the loaded `CoreComponent`:

- **process() invocation**: `Service.process()` calls `self.library_component.process(raw_message)`
- **Return handling**: `bytes` output is forwarded; `None` skips the message

```python
return self.library_component.process(raw_message)
```

### What the Service Expects from CoreComponent

- Constructor accepts optional `config` parameter
- `process(data: bytes) -> bytes | None` method handles message processing
- See [Library Interface Contract](interfaces.md) for the full interface specification

Library-side documentation: [Components architecture](https://ait-detectmate.github.io/DetectMateLibrary/latest/overall_architecture/#components-architecture)
for the class hierarchy, and [Create new component](https://ait-detectmate.github.io/DetectMateLibrary/latest/create_components/)
for writing one.

## CoreConfig

**Import location:** `src/service/core.py`, `src/service/features/config_loader.py`, `src/service/features/config_manager.py`

```python
from detectmatelibrary.common.core import CoreConfig
```

### Usage Points

#### 1. Config Class Loading (`config_loader.py`)

The `ConfigClassLoader` dynamically imports config classes and validates they inherit from `CoreConfig`:

- **Subclass checking**: `issubclass(config_class, CoreConfig)` validates the class hierarchy

```python
if not issubclass(config_class, CoreConfig):
    raise TypeError(...)
```

#### 2. Schema for ConfigManager (`config_manager.py`)

The `ConfigManager` receives the component's `CoreConfig` subclass as its schema:

- **Default creation**: if the config file does not exist, `self.schema()` creates a default config instance and writes it to the file
- **Validation**: config files and `reconfigure` payloads are validated against `ServiceConfig`
- **Serialization**: `to_dict()` (if available) or `model_dump()` converts the config to a dict for YAML storage

```python
# Validation (top-level structure only)
self._configs = ServiceConfig.model_validate(new_configs)

# Serialization
data = self._configs.to_dict()  # falls back to model_dump()
```

#### 3. Service Initialization (`core.py`)

The `Service.get_config_schema()` method returns the appropriate `CoreConfig` subclass for the component.

### What the Service Expects from CoreConfig

- Must be a Pydantic `BaseModel` subclass
- Must support `model_validate(data)` for validation
- Must support `model_dump()` for serialization
- See [Library Interface Contract](interfaces.md) for the full interface specification

Library-side documentation: [Components architecture](https://ait-detectmate.github.io/DetectMateLibrary/latest/overall_architecture/#components-architecture)
for the config class pattern, and [Detectors — Configuration](https://ait-detectmate.github.io/DetectMateLibrary/latest/detectors/#configuration)
for how the library interprets the config contents.

## Protobuf Schemas

**Import location:** Integration tests only (`tests/library_integration/`)

```python
from detectmatelibrary.schemas import LogSchema, ParserSchema, DetectorSchema
```

### Usage Points

The schemas are used in integration tests to verify correct data flow between pipeline stages:

- **LogSchema**: Serialized log lines sent to Parser components by the log source (e.g. Fluentd)
- **ParserSchema**: Serialized output from Parser components
- **DetectorSchema**: Serialized output from Detector components

### Data Flow

```
Log source                Parser                     Detector
   |                         |                          |
   v                         v                          v
LogSchema bytes  --->  ParserSchema bytes  --->  DetectorSchema bytes
```

### What the Service Expects from Schemas

- Protobuf message classes with `SerializeToString()` and `ParseFromString()` methods
- Consistent structure for pipeline interoperability

Library-side documentation: [Schemas](https://ait-detectmate.github.io/DetectMateLibrary/latest/schemas/#schema-clases)
for the `LogSchema` / `ParserSchema` / `DetectorSchema` field definitions.

## Import Resolution

The service uses a two-step import resolution, so short paths like `detectors.RandomDetector` resolve to `detectmatelibrary.detectors.RandomDetector` while custom components from external packages still work. The two loaders try the two prefixes in opposite order:

| Loader | Resolves | Order |
|--------|----------|-------|
| `ComponentLoader` | `component_type` | 1. path as-is → 2. `detectmatelibrary.{path}` |
| `ConfigClassLoader` | `component_config_class` | 1. `detectmatelibrary.{path}` → 2. path as-is |

`component_type` may also be given as a bare class name, see [Component Loading](interfaces.md#component-loading).

## File Reference

| Service File | Library Imports | Purpose |
|--------------|-----------------|---------|
| `src/service/core.py` | `CoreComponent`, `CoreConfig` | Service base class, processor adapter |
| `src/service/features/component_loader.py` | `CoreComponent` | Dynamic component loading |
| `src/service/features/config_loader.py` | `CoreConfig` | Dynamic config class loading |
| `src/service/features/config_manager.py` | `CoreConfig` | Configuration validation and persistence |
