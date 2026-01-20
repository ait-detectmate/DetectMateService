import importlib
from typing import Any, Dict

from detectmatelibrary.common.core import CoreComponent


class ComponentLoader:
    """Loads components dynamically, with DetectMate-relative fallback."""
    DEFAULT_ROOT = "detectmatelibrary"

    @classmethod
    def load_component(
        cls,
        component_type: str,  # "detectors.RandomDetector" or "pkg.mod.Class"
        config: Dict[str, Any] | None = None,
    ) -> CoreComponent:
        """Load a component from the DetectMate library or from any installed
        package.

        Args:
            component_type:
                - DetectMate-style relative path: "detectors.dummy_detector.DummyDetector"
                - OR fully-qualified path:        "somepkg.detectors.FancyDetector"
            config: configuration dictionary / config object for the component

        Returns:
            Initialized component instance
        """
        try:
            # parse component path (e.g. "detectors.dummy_detector.DummyDetector")
            if '.' not in component_type:
                raise ValueError(f"Invalid component type format: {component_type}. "
                                 f"Expected 'module.ClassName or 'package.module.ClassName'")

            module_name, class_name = component_type.rsplit('.', 1)

            # first try as DetectMate-relative
            try:
                full_module_path = f"{cls.DEFAULT_ROOT}.{module_name}"
                module = importlib.import_module(full_module_path)
            except ImportError:
                # If that fails, treat it as an absolute module path
                module = importlib.import_module(module_name)

            # get the class
            component_class = getattr(module, class_name)

            # only pass config if it's truthy ({} behaves as "no config")
            if config:
                instance = component_class(config=config)
            else:
                instance = component_class()

            if not isinstance(instance, CoreComponent):
                raise TypeError(f"Loaded component {component_type} is not a {CoreComponent.__name__}")

            return instance

        except ImportError as e:
            raise ImportError(f"Failed to import component {component_type}: {e}")
        except AttributeError:
            raise AttributeError(f"Component class {class_name} not found in module {module_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to load component {component_type}: {e}")
