import re
from uuid import uuid5, NAMESPACE_URL
from service.settings import ServiceSettings


def test_explicit_component_id_wins():
    explicit = "a" * 32
    s = ServiceSettings(
        component_id=explicit,
        component_name="should_be_ignored",
        component_type="detector",
    )
    assert s.component_id == explicit


def test_uuid5_from_component_name_expected_and_stable():
    s1 = ServiceSettings(component_name="detector-1", component_type="detector")
    expected = uuid5(NAMESPACE_URL, "detectmate/detector/detector-1").hex
    assert s1.component_id == expected

    # Recreate with same inputs -> same ID
    s2 = ServiceSettings(component_name="detector-1", component_type="detector")
    assert s2.component_id == expected


def test_uuid5_from_addresses_expected_and_stable():
    # No component_name -> derive from addresses + type
    s1 = ServiceSettings(
        component_type="detector",
        manager_addr="ipc:///tmp/a.ipc",
        engine_addr="ipc:///tmp/b.ipc",
        component_name=None,
        component_id=None,
    )
    expected = uuid5(
        NAMESPACE_URL,
        "detectmate/detector|ipc:///tmp/a.ipc|ipc:///tmp/b.ipc",
    ).hex
    assert s1.component_id == expected

    # Recreate with same addresses -> same ID
    s2 = ServiceSettings(
        component_type="detector",
        manager_addr="ipc:///tmp/a.ipc",
        engine_addr="ipc:///tmp/b.ipc",
    )
    assert s2.component_id == expected


def test_changing_addresses_changes_id():
    s1 = ServiceSettings(
        component_type="detector",
        manager_addr="ipc:///tmp/a.ipc",
        engine_addr="ipc:///tmp/b.ipc",
    )
    s2 = ServiceSettings(
        component_type="detector",
        manager_addr="ipc:///tmp/c.ipc",  # changed
        engine_addr="ipc:///tmp/b.ipc",
    )
    assert s1.component_id != s2.component_id


def test_same_name_different_type_produces_different_ids():
    s1 = ServiceSettings(component_name="X", component_type="detector")
    s2 = ServiceSettings(component_name="X", component_type="parser")
    assert s1.component_id != s2.component_id


def test_component_id_format_is_hex_32():
    s = ServiceSettings(component_name="abc", component_type="detector")
    assert re.fullmatch(r"[0-9a-f]{32}", s.component_id)


def test_env_vars_drive_component_name(monkeypatch):
    # Pydantic BaseSettings should read DETECTMATE_ prefix
    monkeypatch.setenv("DETECTMATE_COMPONENT_NAME", "env-detector")
    monkeypatch.setenv("DETECTMATE_COMPONENT_TYPE", "detector")

    s = ServiceSettings()
    expected = uuid5(NAMESPACE_URL, "detectmate/detector/env-detector").hex
    assert s.component_id == expected


def test_component_id_overrides_env(monkeypatch):
    monkeypatch.setenv("DETECTMATE_COMPONENT_NAME", "env-name-ignored")
    monkeypatch.setenv("DETECTMATE_COMPONENT_TYPE", "detector")

    explicit = "b" * 32
    s = ServiceSettings(component_id=explicit)
    assert s.component_id == explicit
