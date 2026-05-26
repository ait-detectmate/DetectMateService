"""Tests for TLS configuration models and ServiceSettings cross-validation."""
import pytest
from pydantic import ValidationError

from service.settings import ServiceSettings, TlsInputConfig, TlsOutputConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common non-TLS settings kwargs reused across tests
_BASE = dict(
    engine_addr="ipc:///tmp/test_tls_settings.engine.ipc",
    http_host="127.0.0.1",
    http_port=8099,
    engine_autostart=False,
    log_to_file=False,
)


# ---------------------------------------------------------------------------
# TlsInputConfig model
# ---------------------------------------------------------------------------

def test_tls_input_config_accepts_valid_path(tmp_path):
    """TlsInputConfig constructs correctly with a path to cert_key_file."""
    cert = tmp_path / "server.pem"
    cert.touch()
    cfg = TlsInputConfig(cert_key_file=cert)
    assert cfg.cert_key_file == cert


def test_tls_input_config_requires_cert_key_file():
    """TlsInputConfig raises ValidationError when cert_key_file is missing."""
    with pytest.raises(ValidationError):
        TlsInputConfig()


# ---------------------------------------------------------------------------
# TlsOutputConfig model
# ---------------------------------------------------------------------------

def test_tls_output_config_accepts_valid_ca_file(tmp_path):
    """TlsOutputConfig constructs correctly with just ca_file."""
    ca = tmp_path / "ca.pem"
    ca.touch()
    cfg = TlsOutputConfig(ca_file=ca)
    assert cfg.ca_file == ca
    assert cfg.server_name is None


def test_tls_output_config_accepts_optional_server_name(tmp_path):
    """TlsOutputConfig accepts an optional server_name for SNI override."""
    ca = tmp_path / "ca.pem"
    ca.touch()
    cfg = TlsOutputConfig(ca_file=ca, server_name="detector")
    assert cfg.server_name == "detector"


def test_tls_output_config_requires_ca_file():
    """TlsOutputConfig raises ValidationError when ca_file is missing."""
    with pytest.raises(ValidationError):
        TlsOutputConfig()


# ---------------------------------------------------------------------------
# ServiceSettings cross-validation: missing TLS config blocks
# ---------------------------------------------------------------------------

def test_tls_tcp_engine_addr_without_tls_input_raises():
    """Starting with a tls+tcp engine_addr but no tls_input fails at
    validation."""
    with pytest.raises((ValueError, ValidationError), match="tls_input"):
        ServiceSettings(
            **{**_BASE, "engine_addr": "tls+tcp://0.0.0.0:15000"},
        )


def test_tls_tcp_out_addr_without_tls_output_raises():
    """Having a tls+tcp address in out_addr but no tls_output fails at
    validation."""
    with pytest.raises((ValueError, ValidationError), match="tls_output"):
        ServiceSettings(
            **{**_BASE, "out_addr": ["tls+tcp://detector:15001"]},
        )


def test_tls_tcp_out_addr_mixed_with_non_tls_without_tls_output_raises():
    """Even one tls+tcp address in out_addr requires tls_output to be set."""
    with pytest.raises((ValueError, ValidationError), match="tls_output"):
        ServiceSettings(
            **{**_BASE, "out_addr": [
                "ipc:///tmp/plain.ipc",
                "tls+tcp://detector:15002",
            ]},
        )


# ---------------------------------------------------------------------------
# ServiceSettings cross-validation: valid configurations
# ---------------------------------------------------------------------------

def test_non_tls_addrs_do_not_require_tls_config():
    """Ipc and tcp addresses work fine without any TLS config blocks."""
    settings = ServiceSettings(
        **{**_BASE, "out_addr": ["ipc:///tmp/out.ipc", "tcp://localhost:15003"]},
    )
    assert settings.tls_input is None
    assert settings.tls_output is None


def test_tls_tcp_engine_addr_with_tls_input_is_valid(tmp_path):
    """Tls+tcp engine_addr + tls_input block passes validation."""
    cert = tmp_path / "server.pem"
    cert.touch()
    settings = ServiceSettings(
        **{**_BASE,
           "engine_addr": "tls+tcp://0.0.0.0:15004",
           "tls_input": {"cert_key_file": str(cert)}},
    )
    assert settings.tls_input is not None
    assert settings.tls_input.cert_key_file == cert


def test_tls_tcp_out_addr_with_tls_output_is_valid(tmp_path):
    """Tls+tcp out_addr + tls_output block passes validation."""
    ca = tmp_path / "ca.pem"
    ca.touch()
    settings = ServiceSettings(
        **{**_BASE,
           "out_addr": ["tls+tcp://detector:15005"],
           "tls_output": {"ca_file": str(ca), "server_name": "detector"}},
    )
    assert settings.tls_output is not None
    assert settings.tls_output.server_name == "detector"


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def test_settings_from_yaml_with_tls_input(tmp_path):
    """tls_input block is loaded correctly from a YAML file."""
    cert = tmp_path / "server.pem"
    cert.touch()

    yaml_content = f"""
engine_addr: "tls+tcp://0.0.0.0:15008"
http_host: "127.0.0.1"
http_port: 8100
engine_autostart: false
log_to_file: false
tls_input:
  cert_key_file: "{cert}"
"""
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(yaml_content)

    settings = ServiceSettings.from_yaml(yaml_file)

    assert settings.tls_input is not None
    assert settings.tls_input.cert_key_file == cert


def test_settings_from_yaml_with_tls_output(tmp_path):
    """tls_output block is loaded correctly from a YAML file."""
    ca = tmp_path / "ca.pem"
    ca.touch()

    yaml_content = f"""
engine_addr: "ipc:///tmp/test.ipc"
http_host: "127.0.0.1"
http_port: 8101
engine_autostart: false
log_to_file: false
out_addr:
  - "tls+tcp://detector:15009"
tls_output:
  ca_file: "{ca}"
  server_name: "detector"
"""
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(yaml_content)

    settings = ServiceSettings.from_yaml(yaml_file)

    assert settings.tls_output is not None
    assert settings.tls_output.ca_file == ca
    assert settings.tls_output.server_name == "detector"


def test_settings_from_yaml_tls_tcp_without_config_raises(tmp_path):
    """from_yaml raises SystemExit (wraps ValueError) if tls+tcp addr has no
    TLS block."""
    yaml_content = """
engine_addr: "tls+tcp://0.0.0.0:15010"
http_host: "127.0.0.1"
http_port: 8102
engine_autostart: false
log_to_file: false
"""
    yaml_file = tmp_path / "settings.yaml"
    yaml_file.write_text(yaml_content)

    with pytest.raises(SystemExit):
        ServiceSettings.from_yaml(yaml_file)
