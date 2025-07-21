from pathlib import Path
from uuid import uuid4
from typing import Any, Dict
import yaml
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreComponentSettings(BaseSettings):
    """Settings common to all components.

    Child components inherit & extend this via Pydantic.
    """
    component_id: str = Field(default_factory=lambda: uuid4().hex)
    # TODO: persist somehow, shouldn't change every run!
    # cache? only for comp_id -> manually set for every component
    # if we need more functionality for caching -> think about solutions
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

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "CoreComponentSettings":
        """Utility for one-liner loading w/ override by env vars."""
        if path:
            with open(path, "r") as fh:
                data: Dict[str, Any] = yaml.safe_load(fh) or {}
            try:
                return cls.model_validate(data)
            except ValidationError as e:
                raise SystemExit(f"[config] x {e}") from e
        return cls()
