import importlib
import sys
import types
from pathlib import Path


class LazyModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self._module_path = f".{name}"
        self._module = None

    def _load(self):
        if self._module is None:
            pkg_path = str(Path(__file__).resolve().parent)
            if pkg_path not in sys.path:
                sys.path.append(pkg_path)
            self._module = importlib.import_module(self._module_path, __name__)
        return self._module

    def __getattr__(self, item):
        module = self._load()
        return getattr(module, item)


requests = LazyModule("requests")

__all__ = ["requests"]
