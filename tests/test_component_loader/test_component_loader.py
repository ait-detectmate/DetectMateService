import sys
import types
import pytest

from detectmatelibrary.common.core import CoreComponent
from service.features.component_loader import ComponentLoader


@pytest.fixture(autouse=True)
def cleanup_fake_modules():
    """Automatically clean up any fake modules we add to sys.modules between
    tests."""
    before_keys = set(sys.modules.keys())
    yield
    after_keys = set(sys.modules.keys())
    for key in after_keys - before_keys:
        if key.startswith("testpkg") or key.startswith("anotherpkg"):
            sys.modules.pop(key, None)


def _create_fake_module(module_name: str, class_name: str, init_records: list | None = None):
    """Helper to create a fake module with a single class, injected into
    sys.modules.

    init_records: optional list; if provided, we append received 'config'
                  values to it so tests can assert what was passed.
    """
    module = types.ModuleType(module_name)

    class Dummy(CoreComponent):
        def __init__(self, config=None):
            # record config for assertions if requested
            if init_records is not None:
                init_records.append(config)
            self.config = config

    setattr(module, class_name, Dummy)
    sys.modules[module_name] = module
    return Dummy


def test_load_component_short_path_uses_default_root(monkeypatch):
    """'detectors.RandomDetector' should be resolved as
    '{DEFAULT_ROOT}.detectors.RandomDetector'."""
    # Arrange
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")
    init_records = []
    DummyClass = _create_fake_module(
        module_name="testpkg.detectors",
        class_name="RandomDetector",
        init_records=init_records,
    )
    # Act
    instance = ComponentLoader.load_component(
        "detectors.RandomDetector",
        config={"threshold": 0.7},
    )
    # Assert
    assert isinstance(instance, DummyClass)
    assert instance.config == {"threshold": 0.7}
    assert init_records == [{"threshold": 0.7}]


def test_load_component_full_path_without_default_root(monkeypatch):
    """'anotherpkg.detectors.RandomDetector' should be used as-is, without
    prefixing DEFAULT_ROOT."""
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")  # shouldn't matter
    init_records = []
    DummyClass = _create_fake_module(
        module_name="anotherpkg.detectors",
        class_name="RandomDetector",
        init_records=init_records,
    )
    instance = ComponentLoader.load_component(
        "anotherpkg.detectors.RandomDetector",
        config={"mode": "fast"},
    )
    assert isinstance(instance, DummyClass)
    assert instance.config == {"mode": "fast"}
    assert init_records == [{"mode": "fast"}]


def test_load_component_without_config_calls_default_init(monkeypatch):
    """When config=None, the loader should call the class constructor without
    the 'config' keyword argument."""
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")

    # Track how __init__ is called by storing args/kwargs
    calls = []

    module_name = "testpkg.detectors"

    class Dummy(CoreComponent):
        def __init__(self, *args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})

    module = types.ModuleType(module_name)
    setattr(module, "RandomDetector", Dummy)
    sys.modules[module_name] = module

    instance = ComponentLoader.load_component("detectors.RandomDetector")

    assert isinstance(instance, Dummy)
    # Expect no args and no kwargs, not config=...
    assert calls == [{"args": (), "kwargs": {}}]


def test_load_component_empty_dict_config_behaves_like_no_config(monkeypatch):
    """When config is an empty dict (falsy), the loader should behave like 'no
    config' and NOT pass config=...

    to the constructor.
    """
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")

    calls = []

    module_name = "testpkg.detectors"

    class Dummy(CoreComponent):
        def __init__(self, *args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})

    module = types.ModuleType(module_name)
    setattr(module, "RandomDetector", Dummy)
    sys.modules[module_name] = module

    instance = ComponentLoader.load_component("detectors.RandomDetector", config={})

    assert isinstance(instance, Dummy)
    # Still no args/kwargs – empty dict is treated as "no config"
    assert calls == [{"args": (), "kwargs": {}}]


def test_load_component_invalid_format_raises_runtime_error():
    """Component type without a dot is turned into a ValueError inside the try,
    which is then wrapped as a RuntimeError by the generic except."""
    with pytest.raises(RuntimeError) as excinfo:
        ComponentLoader.load_component("InvalidFormat")

    msg = str(excinfo.value)
    assert "Failed to load component InvalidFormat" in msg
    assert "Invalid component type format" in msg


def test_load_component_missing_module_raises_import_error():
    """Non-existent module path should raise ImportError (wrapped with a custom
    message)."""
    # Make sure the fake module is not present
    sys.modules.pop("nonexistentpkg.detectors", None)

    with pytest.raises(ImportError) as excinfo:
        ComponentLoader.load_component("nonexistentpkg.detectors.RandomDetector")

    msg = str(excinfo.value)
    assert "Failed to import component nonexistentpkg.detectors.RandomDetector" in msg


def test_load_component_missing_class_raises_attribute_error(monkeypatch):
    """Existing module but missing class should raise AttributeError with
    custom message."""
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")

    module_name = "testpkg.detectors"
    module = types.ModuleType(module_name)
    # Intentionally do NOT add RandomDetector
    sys.modules[module_name] = module

    with pytest.raises(AttributeError) as excinfo:
        ComponentLoader.load_component("detectors.RandomDetector")

    msg = str(excinfo.value)
    assert "Component class RandomDetector not found in module detectors" in msg


def test_load_component_type_mismatch_raises_runtime_error(monkeypatch):
    """If the created instance is not an instance of CoreComponent,
    ComponentLoader raises a TypeError inside the try, which is then wrapped as
    a RuntimeError by the generic except."""
    monkeypatch.setattr(ComponentLoader, "DEFAULT_ROOT", "testpkg")

    module_name = "testpkg.detectors"

    class NotABase:
        def __init__(self, config=None):
            self.config = config

    module = types.ModuleType(module_name)
    setattr(module, "RandomDetector", NotABase)
    sys.modules[module_name] = module

    with pytest.raises(RuntimeError) as excinfo:
        ComponentLoader.load_component("detectors.RandomDetector", config={})

    msg = str(excinfo.value)
    assert "Failed to load component detectors.RandomDetector" in msg
    assert "not a CoreComponent" in msg
