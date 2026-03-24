import importlib
import logging
from typing import Type, cast

from detectmatelibrary.common.core import CoreConfig

log = logging.getLogger(__name__)


class ConfigClassLoader:
    """Loads configuration schema classes from DetectMate library
    dynamically."""

    BASE_PACKAGE = "detectmatelibrary"

    @classmethod
    def load_config_class(cls,
                          config_class_path: str,
                          logger: logging.Logger | None = None) -> Type[CoreConfig]:
        """Load a config class from a path string.

        Args:
            config_class_path: dot path like "readers.log_file.LogFileConfig"
                               or fully-qualified like "myplugin.readers.LogFileConfig"

        Returns:
            The config class (not an instance)

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If class not found in module
            TypeError: If class is not a subclass of CoreConfig
            RuntimeError: For other failures (e.g. invalid format)
        """
        log = logger or logging.getLogger(__name__)
        log.debug("Loading config class: %r", config_class_path)
        try:
            # handle "module.ClassName" formats
            if '.' not in config_class_path:
                raise ValueError(
                    f"Invalid config class format: {config_class_path}. "
                    f"Expected 'module.ClassName'"
                )

            module_name, class_name = config_class_path.rsplit('.', 1)
            log.debug("Parsed: module=%r  class=%r", module_name, class_name)

            # Avoid double-prefixing if already fully qualified
            if module_name.startswith(f"{cls.BASE_PACKAGE}.") or module_name == cls.BASE_PACKAGE:
                log.debug("Path is already fully qualified, importing directly")
                try:
                    module = importlib.import_module(module_name)
                except ImportError as e:
                    raise ImportError(f"Failed to import config class {config_class_path}: {e}") from e
            else:
                prefixed = f"{cls.BASE_PACKAGE}.{module_name}"
                try:
                    module = importlib.import_module(prefixed)
                    log.debug("Imported via library-relative path: %r", prefixed)
                except ImportError:
                    log.debug("Library-relative import failed, falling back to absolute: %r", module_name)
                    module = importlib.import_module(module_name)  # absolute fallback
                    log.debug("Imported via absolute path: %r", module_name)

            # get the class
            config_class = getattr(module, class_name)

            if not issubclass(config_class, CoreConfig):
                raise TypeError(f"Config class {class_name} must inherit from CoreConfig")

            return cast(Type[CoreConfig], config_class)

        except ImportError as e:
            raise ImportError(f"Failed to import config class {config_class_path}: {e}") from e
        except AttributeError as e:
            raise AttributeError(f"Config class {class_name} not found in module {module_name}") from e
        except TypeError as e:
            raise TypeError(str(e)) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load config class {config_class_path}: {e}") from e
