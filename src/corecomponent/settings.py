from pathlib import Path
from uuid import uuid4
from typing import Any, Dict
import yaml
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreComponentSettings(BaseSettings):
    """
    Settings common to all components.
    Child components inherit & extend this via Pydantic.
    """
    component_id: str = Field(default_factory=lambda: uuid4().hex)
    component_type: str = "core"  # e.g. detector, parser, etc

    # logger
    log_dir: Path = Path("./logs")
    log_to_console: bool = True
    log_to_file: bool = True
    log_level: str = "INFO"

    # MQ defaults
    mq_addr_in: str | None = "ipc:///tmp/detectmate.in.ipc"
    mq_addr_out: str | None = "ipc:///tmp/detectmate.out.ipc"

    model_config = SettingsConfigDict(
        env_prefix="DETECTMATE_",   # DETECTMATE_LOG_LEVEL etc.
        env_nested_delimiter="__",  # DETECTMATE_DETECTOR__THRESHOLD
        extra="forbid",
    )

    @classmethod
    def from_yaml(cls, path: str | Path | None) -> "CoreSettings":
        """Utility for one-liner loading w/ override by env vars."""
        if path:
            with open(path, "r") as fh:
                data: Dict[str, Any] = yaml.safe_load(fh) or {}
            try:
                return cls.model_validate(data)
            except ValidationError as e:
                raise SystemExit(f"[config] x {e}") from e
        return cls()  # all defaults
