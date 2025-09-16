from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional


class BaseSettingsSchema(BaseModel):
    """Base schema for service settings."""
    component_name: Optional[str] = Field(
        default=None,
        description="Stable name for the component (preferred over component_id)"
    )
    component_id: Optional[str] = Field(
        default=None,
        description="Explicit component ID (computed if not provided)"
    )
    component_type: str = Field(
        default="core",
        description="Type of component (e.g., detector, parser, etc.)"
    )
    log_dir: Path = Field(
        default=Path("./logs"),
        description="Directory for log files"
    )
    log_to_console: bool = Field(
        default=True,
        description="Whether to log to console"
    )
    log_to_file: bool = Field(
        default=True,
        description="Whether to log to file"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    manager_addr: Optional[str] = Field(
        default="ipc:///tmp/detectmate.cmd.ipc",
        description="Manager command channel address"
    )
    manager_recv_timeout: int = Field(
        default=100,
        description="Manager receive timeout in milliseconds"
    )
    engine_addr: Optional[str] = Field(
        default="ipc:///tmp/detectmate.engine.ipc",
        description="Engine channel address"
    )
    engine_autostart: bool = Field(
        default=True,
        description="Whether to autostart the engine"
    )
    engine_recv_timeout: int = Field(
        default=100,
        description="Engine receive timeout in milliseconds"
    )
    parameter_file: Optional[Path] = Field(
        default=None,
        description="Path to parameter file"
    )
