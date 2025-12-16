import sys
import types
import pytest

from detectmatelibrary.common.core import CoreConfig
from service.features.config_loader import ConfigClassLoader


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


def _create_fake_module(module_name: str, class_name: str, base=CoreConfig):
    """Helper to create a fake module with a single config class.

    base: base class to inherit from (default: CoreConfig; use object for
          type-mismatch tests).
    """
    module = types.ModuleType(module_name)

    class DummyConfig(base):
        pass

    setattr(module, class_name, DummyConfig)
    sys.modules[module_name] = module
    return DummyConfig


def test_load_config_class_short_path_uses_base_package(monkeypatch):
    """'readers.log_file.LogFileConfig' should be resolved as
    '{BASE_PACKAGE}.readers.log_file.LogFileConfig'."""
    monkeypatch.setattr(ConfigClassLoader, "BASE_PACKAGE", "testpkg")

    DummyClass = _create_fake_module(
        module_name="testpkg.readers.log_file",
        class_name="LogFileConfig",
    )

    result = ConfigClassLoader.load_config_class(
        "readers.log_file.LogFileConfig"
    )

    assert result is DummyClass
    assert issubclass(result, CoreConfig)


def test_load_config_class_full_path_uses_absolute_module(monkeypatch):
    """'anotherpkg.readers.log_file.LogFileConfig' should be imported as
    'anotherpkg.readers.log_file', even though BASE_PACKAGE is set."""
    monkeypatch.setattr(ConfigClassLoader, "BASE_PACKAGE", "testpkg")  # shouldn't affect absolute path

    DummyClass = _create_fake_module(
        module_name="anotherpkg.readers.log_file",
        class_name="LogFileConfig",
    )

    result = ConfigClassLoader.load_config_class(
        "anotherpkg.readers.log_file.LogFileConfig"
    )

    assert result is DummyClass
    assert issubclass(result, CoreConfig)


def test_load_config_class_invalid_format_raises_runtime_error():
    """Config class path without a dot raises ValueError in the try-block,
    which is then wrapped as a RuntimeError by the generic except."""
    with pytest.raises(RuntimeError) as excinfo:
        ConfigClassLoader.load_config_class("InvalidFormat")

    msg = str(excinfo.value)
    assert "Failed to load config class InvalidFormat" in msg
    assert "Invalid config class format" in msg


def test_load_config_class_missing_module_raises_import_error():
    """Non-existent module path should raise ImportError (wrapped with a custom
    message)."""
    # Make sure the fake module is not present
    sys.modules.pop("nonexistentpkg.readers.log_file", None)
    sys.modules.pop("testpkg.nonexistentpkg.readers.log_file", None)

    with pytest.raises(ImportError) as excinfo:
        ConfigClassLoader.load_config_class(
            "nonexistentpkg.readers.log_file.LogFileConfig"
        )

    msg = str(excinfo.value)
    assert "Failed to import config class nonexistentpkg.readers.log_file.LogFileConfig" in msg


def test_load_config_class_missing_class_raises_attribute_error(monkeypatch):
    """Existing module but missing class should raise AttributeError with
    custom message."""
    monkeypatch.setattr(ConfigClassLoader, "BASE_PACKAGE", "testpkg")

    module_name = "testpkg.readers.log_file"
    module = types.ModuleType(module_name)
    # Intentionally do NOT add LogFileConfig
    sys.modules[module_name] = module

    with pytest.raises(AttributeError) as excinfo:
        ConfigClassLoader.load_config_class("readers.log_file.LogFileConfig")

    msg = str(excinfo.value)
    assert "Config class LogFileConfig not found in module readers.log_file" in msg


def test_load_config_class_type_mismatch_raises_type_error(monkeypatch):
    """If the loaded class is not a subclass of CoreConfig, ConfigClassLoader
    raises a TypeError with a clear message."""
    monkeypatch.setattr(ConfigClassLoader, "BASE_PACKAGE", "testpkg")

    # Create a module where LogFileConfig does NOT inherit from CoreConfig
    module_name = "testpkg.readers.log_file"
    _create_fake_module(
        module_name=module_name,
        class_name="LogFileConfig",
        base=object,  # <- not CoreConfig
    )

    with pytest.raises(TypeError) as excinfo:
        ConfigClassLoader.load_config_class("readers.log_file.LogFileConfig")

    msg = str(excinfo.value)
    assert "Config class LogFileConfig must inherit from CoreConfig" in msg
