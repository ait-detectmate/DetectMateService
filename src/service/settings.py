from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from typing import Any, Dict, Optional
import yaml
from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    """Settings common to all services.

    Child services inherit & extend this via Pydantic.
    """

    # Give each instance either a stable name or explicit id via config/env.
    # DETECTMATE_COMPONENT_NAME=detector-1 (preferred)
    # or DETECTMATE_COMPONENT_ID=... (explicit)
    component_name: Optional[str] = None
    component_id: Optional[str] = None  # computed if not provided
    component_type: str = "core"  # e.g. detector, parser, etc

    # logger
    log_dir: Path = Path("./logs")
    log_to_console: bool = True
    log_to_file: bool = True
    log_level: str = "INFO"

    # Manager (command) channel (REQ/REP)
    manager_addr: str | None = "ipc:///tmp/detectmate.cmd.ipc"

    # Engine channel (PAIR0)
    engine_addr: str | None = "ipc:///tmp/detectmate.engine.ipc"
    engine_autostart: bool = True

    model_config = SettingsConfigDict(
        env_prefix="DETECTMATE_",   # DETECTMATE_LOG_LEVEL etc.
        env_nested_delimiter="__",  # DETECTMATE_DETECTOR__THRESHOLD
        extra="forbid",
    )

    @model_validator(mode="after")
    def _ensure_component_id(self):
        # If user provided explicitly, keep it.
        if self.component_id:
            return self

        # 1) Prefer a stable name -> stable UUIDv5
        if self.component_name:
            name = f"detectmate/{self.component_type}/{self.component_name}"
            self.component_id = uuid5(NAMESPACE_URL, name).hex
            return self

        # 2) No name: derive deterministically from addresses (also stable)
        #    This stays the same as long as the addresses don't change.
        base = f"{self.component_type}|{self.manager_addr or ''}|{self.engine_addr or ''}"
        self.component_id = uuid5(NAMESPACE_URL, f"detectmate/{base}").hex
        return self

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "ServiceSettings":
        """Utility for one-liner loading w/ override by env vars."""
        if path:
            with open(path, "r") as fh:
                data: Dict[str, Any] = yaml.safe_load(fh) or {}
            try:
                return cls.model_validate(data)
            except ValidationError as e:
                raise SystemExit(f"[config] x {e}") from e
        return cls()
