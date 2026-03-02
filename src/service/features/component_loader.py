import importlib
from typing import Any, Dict
import logging

from detectmatelibrary.common.core import CoreComponent
from logging import Logger


class ComponentLoader:
    """Loads components dynamically, with DetectMate-relative fallback."""

    DEFAULT_ROOT = "detectmatelibrary"

    @classmethod
    def load_component(cls,
                       component_type: str, config: Dict[str, Any] | None = None,
                       logger: Logger | None = None) -> CoreComponent:
        """Load a component from a fully-qualified dotted path.

        Expects ComponentResolver.resolve() to have already been called —
        component_type must be a fully-qualified path from the library
        (or installed package) like:
        'detectmatelibrary.detectors.new_value_detector.NewValueComboDetector'
        """
        log = logger or logging.getLogger(__name__)
        try:
            if '.' not in component_type:
                raise ValueError(
                    f"Invalid component type: {component_type}. "
                    f"ComponentResolver.resolve() must be called before load_component()."
                )

            module_name, class_name = component_type.rsplit('.', 1)
            log.debug("Importing module %r, class %r", module_name, class_name)
            # Try as-is first, then fall back to detectmatelibrary-relative
            try:
                module = importlib.import_module(module_name)
            except ImportError:
                full_module = f"{cls.DEFAULT_ROOT}.{module_name}"
                log.debug("Direct import failed, retrying as %r", full_module)
                try:
                    module = importlib.import_module(full_module)
                except ImportError:
                    raise ImportError(f"Could not import '{module_name}' or '{full_module}'")

            component_class = getattr(module, class_name)

            if config:
                instance = component_class(config=config)
            else:
                instance = component_class()

            if not isinstance(instance, CoreComponent):
                raise TypeError(
                    f"Loaded component {component_type!r} is not a {CoreComponent.__name__}"
                )
            return instance

        except ImportError as e:
            raise ImportError(f"Failed to import component {component_type}: {e}")
        except AttributeError:
            raise AttributeError(f"Component Class {class_name} not found in module {module_name}")
        except TypeError as e:
            raise RuntimeError(f"Failed to load component {component_type}: {e}") from e
        except ValueError as e:
            raise RuntimeError(f"Failed to load component {component_type}: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to load component {component_type}: {e}") from e
