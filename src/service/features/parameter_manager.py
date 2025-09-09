import os
import yaml
import threading
from pathlib import Path
from typing import Type, Optional, Dict, Any, Union
from pydantic import BaseModel, ValidationError

from service.features.parameters import BaseParameters


class ParameterManager:
    def __init__(self, param_file: str, schema: Optional[Type[BaseParameters]] = None):
        self.param_file = param_file
        self.schema = schema
        self._params: Optional[Union[BaseParameters, Dict[str, Any]]] = None
        self._lock = threading.RLock()

        # Load initial parameters
        self.load()

    def load(self) -> None:
        """Load parameters from file."""
        if not os.path.exists(self.param_file):
            # Create default parameters if file doesn't exist
            if self.schema:
                self._params = self.schema()
                self.save()
            return

        try:
            with open(self.param_file, 'r') as f:
                data = yaml.safe_load(f)

            if self.schema and data:
                self._params = self.schema.model_validate(data)
            elif data:
                # If no schema, store as raw dict
                self._params = data

        except (yaml.YAMLError, ValidationError) as e:
            # Handle invalid YAML or validation errors
            raise ValueError(f"Failed to load parameters from {self.param_file}: {e}")

    def save(self) -> None:
        """Save parameters to file."""
        with self._lock:
            if self._params is None:
                return

            # Ensure directory exists
            Path(self.param_file).parent.mkdir(parents=True, exist_ok=True)

            # Convert to dict for YAML serialization
            if isinstance(self._params, BaseModel):
                data = self._params.model_dump()
            else:
                data = self._params

            with open(self.param_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False)

    def update(self, new_params: Dict[str, Any]) -> None:
        """Update parameters with validation."""
        with self._lock:
            if self.schema:
                self._params = self.schema.model_validate(new_params)
            else:
                self._params = new_params

    def get(self) -> Optional[Union[BaseParameters, Dict[str, Any]]]:
        """Get current parameters."""
        with self._lock:
            return self._params
