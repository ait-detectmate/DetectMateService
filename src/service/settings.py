import os
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
from typing import Any, Dict, Optional
import yaml
from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from service.schemas.settings import BaseSettingsSchema


class ServiceSettings(BaseSettings):
    """Settings common to all services."""

    component_name: Optional[str] = BaseSettingsSchema.model_fields["component_name"].default
    component_id: Optional[str] = BaseSettingsSchema.model_fields["component_id"].default
    component_type: str = BaseSettingsSchema.model_fields["component_type"].default
    log_dir: Path = BaseSettingsSchema.model_fields["log_dir"].default
    log_to_console: bool = BaseSettingsSchema.model_fields["log_to_console"].default
    log_to_file: bool = BaseSettingsSchema.model_fields["log_to_file"].default
    log_level: str = BaseSettingsSchema.model_fields["log_level"].default
    manager_addr: str | None = BaseSettingsSchema.model_fields["manager_addr"].default
    manager_recv_timeout: int = BaseSettingsSchema.model_fields["manager_recv_timeout"].default
    engine_addr: str | None = BaseSettingsSchema.model_fields["engine_addr"].default
    engine_autostart: bool = BaseSettingsSchema.model_fields["engine_autostart"].default
    engine_recv_timeout: int = BaseSettingsSchema.model_fields["engine_recv_timeout"].default
    parameter_file: Optional[Path] = BaseSettingsSchema.model_fields["parameter_file"].default

    model_config = SettingsConfigDict(
        env_prefix="DETECTMATE_",  # DETECTMATE_LOG_LEVEL etc.
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
        data: Dict[str, Any] = {}
        if path:
            path = Path(path)
            if path.exists():
                with open(path, "r") as fh:
                    data = yaml.safe_load(fh) or {}

        # convert string paths to Path objects
        if "log_dir" in data and isinstance(data["log_dir"], str):
            data["log_dir"] = Path(data["log_dir"])

        # check which fields have environment variable values
        env_fields = set()
        for field in cls.model_fields:
            env_name = f"{cls.model_config['env_prefix']}{field.upper()}"
            if env_name in os.environ:
                env_fields.add(field)

        # create a dictionary with final values (env vars override yaml)
        final_data = {}
        for field in cls.model_fields:
            if field in env_fields:
                # get the value from environment (let Pydantic handle parsing)
                env_name = f"{cls.model_config['env_prefix']}{field.upper()}"
                final_data[field] = os.environ[env_name]
            elif field in data:
                final_data[field] = data[field]  # use yaml value if no env var
            else:
                continue  # pydantic will handle default values

        try:
            return cls.model_validate(final_data)
        except ValidationError as e:
            raise SystemExit(f"[config] x {e}") from e
