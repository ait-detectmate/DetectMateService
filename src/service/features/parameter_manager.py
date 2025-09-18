import os
import yaml
import threading
import logging
from pathlib import Path
from typing import Type, Optional, Dict, Any, Union
from pydantic import BaseModel, ValidationError

from service.features.parameters import BaseParameters


class ParameterManager:
    def __init__(
            self,
            param_file: str,
            schema: Optional[Type[BaseParameters]] = None,
            logger: Optional[logging.Logger] = None
    ):
        self.param_file = param_file
        self.schema = schema
        self._params: Optional[Union[BaseParameters, Dict[str, Any]]] = None
        self._lock = threading.RLock()
        self.logger = logger or logging.getLogger(__name__)

        # Load initial parameters
        self.load()

    def load(self) -> None:
        """Load parameters from file."""
        self.logger.debug(f"Loading parameters from {self.param_file}")
        if not os.path.exists(self.param_file):
            self.logger.info(f"Parameter file {self.param_file} doesn't exist, creating default")
            # Create default parameters if file doesn't exist
            if self.schema:
                self._params = self.schema()
                self.logger.debug(f"Created default params: {self._params}")
                self.save()
            else:
                self.logger.warning("No schema provided, cannot create default parameters")
            return

        try:
            with open(self.param_file, 'r') as f:
                data = yaml.safe_load(f)
            self.logger.debug(f"Loaded data from file: {data}")

            if self.schema and data:
                self._params = self.schema.model_validate(data)
                self.logger.debug(f"Validated params: {self._params}")
            elif data:
                # If no schema, store as raw dict
                self._params = data
                self.logger.debug(f"Stored raw data: {self._params}")

        except (yaml.YAMLError, ValidationError) as e:
            self.logger.error(f"Failed to load parameters from {self.param_file}: {e}")
            raise

    def save(self) -> None:
        """Save parameters to file."""
        # TODO: only do this when there is a parameter in the reconfig command to persist
        with self._lock:
            if self._params is None:
                return

            # Ensure directory exists with proper error handling
            param_dir = Path(self.param_file).parent
            try:
                param_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.logger.error(f"Permission denied creating directory {param_dir}")
                raise
            except OSError as e:
                self.logger.error(f"Failed to create directory {param_dir}: {e}")
                raise

            # Convert to dict for YAML serialization
            if isinstance(self._params, BaseModel):
                data = self._params.model_dump()
            else:
                data = self._params

            try:
                with open(self.param_file, 'w') as f:
                    yaml.dump(data, f, default_flow_style=False)
                self.logger.debug(f"Parameters saved to {self.param_file}")
            except PermissionError:
                self.logger.error(f"Permission denied writing to file {self.param_file}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to save parameters to {self.param_file}: {e}")
                raise

    def update(self, new_params: Dict[str, Any]) -> None:
        """Update parameters with validation."""
        with self._lock:
            if self.schema:
                self._params = self.schema.model_validate(new_params)
            else:
                self._params = new_params
            self.logger.info(f"Parameters updated: {self._params}")

    def get(self) -> Optional[Union[BaseParameters, Dict[str, Any]]]:
        """Get current parameters."""
        with self._lock:
            return self._params
