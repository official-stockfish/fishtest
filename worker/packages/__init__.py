import importlib
import sys
from pathlib import Path

__all__ = ["requests"]


def __getattr__(name):
    if name in __all__:
        pkg_path = str(Path(__file__).resolve().parent)
        if pkg_path not in sys.path:
            sys.path.insert(0, pkg_path)
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
