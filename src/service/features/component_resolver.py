# service/features/component_resolver.py
from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Optional, Tuple

from detectmatelibrary.common.core import CoreComponent

_LIBRARY_ROOT = "detectmatelibrary"


class ComponentResolver:
    """Resolves a short component name (e.g. 'NewValueComboDetector') to a
    fully-qualified path and its corresponding Config class.

    Already fully-qualified paths (with a dot) are returned as-is and we try to
    get the config class from the same module.
    For Short names wewalk the sub-modules of `detectmatelibrary` and find
    a class whose __name__ matches.

    Example:
    Given class FooDetector in module detectmatelibrary.detectors.foo,
    the resolver looks for FooDetectorConfig in the same module (!).
    Fall back to CoreConfig if nothing is found.
    """

    @classmethod
    def resolve(
        cls,
        component_type: str,
    ) -> Tuple[str, str]:
        """Return (full_component_path, full_config_class_path).

        Parameters
        ----------
        component_type:
            Either a short class name "NewValueComboDetector" (resolved by searching the library)
            or a dotted path "detectors.new_value_detector.NewValueComboDetector" (return as is)
        """
        if "." in component_type:
            # Already a dotted path - return as is and try to find the config in the same module
            module_path, class_name = component_type.rsplit(".", 1)
            config_path = cls._find_config_in_module(module_path, class_name)
            return component_type, config_path

        # Short name — look for it in the library
        result = cls._search_for_class(component_type)
        if result is None:
            raise ImportError(
                f"Could not find a component named '{component_type}' "
                f"anywhere under '{_LIBRARY_ROOT}'. "
                f"Use the full dotted path."
            )
        full_component_path, module_path, class_name = result
        config_path = cls._find_config_in_module(module_path, class_name)
        return full_component_path, config_path

    @classmethod
    def _search_for_class(
        cls, class_name: str
    ) -> Optional[Tuple[str, str, str]]:
        """Search detectmatelibrary and return the first module that exports a
        CoreComponent subclass with the given name.

        Returns (dotted_component_path, dotted_module_path, class_name)
        or None.
        """
        try:
            root_pkg = importlib.import_module(_LIBRARY_ROOT)
        except ImportError:
            return None

        for finder, module_name, _ in pkgutil.walk_packages(
            path=root_pkg.__path__,
            prefix=f"{_LIBRARY_ROOT}.",
            onerror=lambda _: None,
        ):
            try:
                module = importlib.import_module(module_name)
            except Exception:  # nosec B112
                continue

            klasse = getattr(module, class_name, None)
            if klasse is None:
                continue
            if not (inspect.isclass(klasse) and issubclass(klasse, CoreComponent) and
                    klasse is not CoreComponent):
                continue

            # Found it:
            return f"{module_name}.{class_name}", module_name, class_name

        return None

    @classmethod
    def _find_config_in_module(cls, module_path: str, class_name: str) -> str:
        """Look for <ClassName>Config in the same module.

        Falls back to the CoreConfig path.
        """
        config_name = f"{class_name}Config"
        fallback = "detectmatelibrary.common.core.CoreConfig"

        # Avoid double-prefixing if already fully qualified
        candidates: tuple[str, ...]
        if module_path.startswith(f"{_LIBRARY_ROOT}.") or module_path == _LIBRARY_ROOT:
            candidates = (module_path,)
        else:
            candidates = (f"{_LIBRARY_ROOT}.{module_path}", module_path)

        for candidate_path in candidates:
            try:
                module = importlib.import_module(candidate_path)
            except ImportError:
                continue

            klasse = getattr(module, config_name, None)
            if klasse is not None and inspect.isclass(klasse):
                return f"{candidate_path}.{config_name}"

        return fallback
