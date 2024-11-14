import sys
import importlib.util
from types import ModuleType


def lazy_import(fullname: str) -> ModuleType:
    if fullname in sys.modules:
        return sys.modules[fullname]

    spec = importlib.util.find_spec(fullname)
    if spec is None:
        raise ValueError(f"{spec} module not found")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    # Make module with proper locking and get it inserted into sys.modules.
    loader.exec_module(module)
    sys.modules[fullname] = module
    return module
