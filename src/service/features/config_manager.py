import os
import yaml
import threading
import logging
from pathlib import Path
from typing import Type, Optional, Dict, Any, Union
from pydantic import BaseModel, ValidationError

from service.features.config import BaseConfig


class ConfigManager:
    def __init__(
            self,
            config_file: str,
            schema: Optional[Type[BaseConfig]] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.config_file = config_file
        self.schema = schema
        self._configs: Optional[Union[BaseConfig, Dict[str, Any]]] = None
        self._lock = threading.RLock()
        self.logger = logger or logging.getLogger(__name__)

        # Load initial parameters
        self.load()

    def load(self) -> None:
        """Load parameters from file."""
        self.logger.debug(f"Loading parameters from {self.config_file}")
        if not os.path.exists(self.config_file):
            self.logger.info(f"Parameter file {self.config_file} doesn't exist, creating default")
            # Create default parameters if file doesn't exist
            if self.schema:
                self._configs = self.schema()
                self.logger.debug(f"Created default params: {self._configs}")
                self.save()
            else:
                self.logger.warning("No schema provided, cannot create default parameters")
            return

        try:
            with open(self.config_file, 'r') as f:
                data = yaml.safe_load(f)
            self.logger.debug(f"Loaded data from file: {data}")

            if self.schema and data:
                self._configs = self.schema.model_validate(data)
                self.logger.debug(f"Validated params: {self._configs}")
            elif data:
                # If no schema, store as raw dict
                self._configs = data
                self.logger.debug(f"Stored raw data: {self._configs}")

        except (yaml.YAMLError, ValidationError) as e:
            self.logger.error(f"Failed to load parameters from {self.config_file}: {e}")
            raise

    def save(self) -> None:
        """Save parameters to file."""
        with self._lock:
            if self._configs is None:
                return

            # Ensure directory exists with proper error handling
            param_dir = Path(self.config_file).parent
            try:
                param_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.logger.error(f"Permission denied creating directory {param_dir}")
                raise
            except OSError as e:
                self.logger.error(f"Failed to create directory {param_dir}: {e}")
                raise

            # Convert to dict for YAML serialization
            if isinstance(self._configs, BaseModel):
                data = self._configs.model_dump()
            else:
                data = self._configs

            try:
                with open(self.config_file, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False)
                self.logger.debug(f"Parameters saved to {self.config_file}")
            except PermissionError:
                self.logger.error(f"Permission denied writing to file {self.config_file}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to save parameters to {self.config_file}: {e}")
                raise

    def update(self, new_configs: Dict[str, Any]) -> None:
        """Update parameters with validation."""
        with self._lock:
            if self.schema:
                self._configs = self.schema.model_validate(new_configs)
            else:
                self._configs = new_configs
            self.logger.info(f"Parameters updated: {self._configs}")

    def get(self) -> Optional[Union[BaseConfig, Dict[str, Any]]]:
        """Get current parameters."""
        with self._lock:
            return self._configs
