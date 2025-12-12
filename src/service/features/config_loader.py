import importlib
from typing import Type, cast


from detectmatelibrary.common.core import CoreConfig


class ConfigClassLoader:
    """Loads configuration schema classes from DetectMate library
    dynamically."""

    @classmethod
    def load_config_class(cls, config_class_path: str) -> Type[CoreConfig]:
        """Load a config class from a path string.

        Args:
            config_class_path: dot path like "readers.log_file.LogFileConfig"
                             or just class name if in detectmatelibrary

        Returns:
            The config class (not an instance)

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If class not found in module
        """
        try:
            # handle both "module.ClassName" and just "ClassName" formats
            if '.' not in config_class_path:
                raise ValueError(
                    f"Invalid config class format: {config_class_path}. "
                    f"Expected 'module.ClassName'"
                )

            module_name, class_name = config_class_path.rsplit('.', 1)

            # import the module
            full_module_path = f"detectmatelibrary.{module_name}"
            module = importlib.import_module(full_module_path)

            # get the class
            config_class = getattr(module, class_name)
            config_class = cast(Type[CoreConfig], config_class)  # help mypy

            if not issubclass(config_class, CoreConfig):
                raise TypeError(f"Config class {class_name} must inherit from CoreConfig")

            return config_class

        except ImportError as e:
            raise ImportError(f"Failed to import config class {config_class_path}: {e}") from e
        except AttributeError as e:
            raise AttributeError(f"Config class {class_name} not found in module {module_name}") from e
        except TypeError as e:
            raise TypeError(str(e)) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load config class {config_class_path}: {e}") from e
