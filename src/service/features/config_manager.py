import os
import yaml
import threading
import logging
from pathlib import Path
from typing import Type, Optional, Dict, Any, Union
from pydantic import BaseModel, ValidationError

from detectmatelibrary.common.core import CoreConfig


class ServiceConfig(BaseModel):
    detectors: Optional[Dict[str, Dict[str, Any]]] = None
    parsers: Optional[Dict[str, Dict[str, Any]]] = None


class ConfigManager:
    def __init__(
            self,
            config_file: str,
            schema: Optional[Type[CoreConfig]] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.config_file = config_file
        self.schema = schema
        self._configs: Optional[Union[CoreConfig, Dict[str, Any]]] = None
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
                # Problem: mismatch between component config schema and structure the library expects
                # cannot validate against self.schema
                # self.schema does not accept "detectors" or "parsers" key which the library expects
                # cannot nest, because self.schema does not accept a params field, which the library expects
                # --> validate against ServiceConfig here, let library handle the rest

                self._configs = ServiceConfig.model_validate(data)
                self.logger.debug(f"Validated params: {self._configs}")
            elif data:
                # If no schema, store as raw dict
                self._configs = data
                self.logger.debug(f"Stored raw data: {self._configs}")

        except (yaml.YAMLError, ValidationError) as e:
            self.logger.error(f"Failed to load parameters from {self.config_file}: {e}")
            raise

    def save(self, config_dict: Optional[Dict[str, Any]] = None) -> None:
        """Save component configs to file.

        Args:
            config_dict: Optional dict to save directly. If None, serializes
                        current config model using to_dict() if available,
                        otherwise model_dump().
        """
        with self._lock:
            if config_dict is not None:
                data = config_dict
                self.logger.debug("Saving provided config dict")
            elif self._configs is None:
                return
            elif isinstance(self._configs, BaseModel):
                # Prefer to_dict() over model_dump() to avoid defaults
                if hasattr(self._configs, 'to_dict'):
                    data = self._configs.to_dict()
                    self.logger.debug("Using to_dict() for serialization")
                else:
                    data = self._configs.model_dump()
                    self.logger.debug("Using model_dump() for serialization")
            else:
                # Already a dict
                data = self._configs

            param_dir = Path(self.config_file).parent
            try:
                param_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.logger.error(f"Permission denied creating directory {param_dir}")
                raise
            except OSError as e:
                self.logger.error(f"Failed to create directory {param_dir}: {e}")
                raise

        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
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
                self._configs = ServiceConfig.model_validate(new_configs)
            else:
                self._configs = new_configs
            self.logger.info(f"Parameters updated: {self._configs}")

    def get(self) -> Optional[Union[CoreConfig, Dict[str, Any]]]:
        """Get current parameters."""
        with self._lock:
            return self._configs
