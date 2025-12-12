"""Tests for ensuring DetectMateLibrary is imported correctly."""


def test_import_core_components():
    """Test that core components can be imported successfully."""
    # this will fail at import time if the package isn't available
    from detectmatelibrary.common.core import CoreComponent, CoreConfig
    assert CoreComponent is not None
    assert CoreConfig is not None


def test_core_config_creation():
    """Test CoreConfig instantiation and attributes."""
    from detectmatelibrary.common.core import CoreConfig
    config = CoreConfig(start_id=100)
    assert config.start_id == 100


def test_core_component_creation():
    """Test CoreComponent instantiation with config."""
    from detectmatelibrary.common.core import CoreComponent, CoreConfig

    config = CoreConfig(start_id=100)
    component = CoreComponent(name="test_component", config=config)

    assert component.name == "test_component"
    assert component.config.start_id == 100
