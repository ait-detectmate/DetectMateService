import importlib
from typing import Any, Dict


from detectmatelibrary.common.core import CoreComponent


class ComponentLoader:
    """Loads components from the DetectMate library dynamically."""

    @classmethod
    def load_component(cls, component_type: str, config: Dict[str, Any] | None = None) -> CoreComponent:
        """Load a component from the DetectMate library.

        Args:
            component_type: dot path like "detectors.RandomDetector"
            config: configuration dictionary for the component

        Returns:
            Initialized component instance
        """
        try:
            # parse component path (e.g. "detectors.RandomDetector")
            if '.' not in component_type:
                raise ValueError(f"Invalid component type format: {component_type}. "
                                 f"Expected 'module.ClassName'")

            module_name, class_name = component_type.rsplit('.', 1)

            # import the module
            full_module_path = f"detectmatelibrary.{module_name}"
            module = importlib.import_module(full_module_path)

            # get the class
            component_class = getattr(module, class_name)

            # create instance with config if provided
            if config:
                instance = component_class(config=config)
            else:
                instance = component_class()

            return instance

        except ImportError as e:
            raise ImportError(f"Failed to import component {component_type}: {e}")
        except AttributeError:
            raise AttributeError(f"Component class {class_name} not found in module {module_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to load component {component_type}: {e}")
