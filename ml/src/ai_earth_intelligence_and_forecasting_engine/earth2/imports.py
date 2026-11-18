from __future__ import annotations

import importlib
import importlib.util
import sys
import types

DATA_NAMES = {"fetch_data": "utils", "ARCO": "arco", "GFS": "gfs"}


def package_without_init(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.find_spec(name)
    if spec is None or spec.submodule_search_locations is None:
        raise ImportError(f"{name} is not a package")
    module = types.ModuleType(name)
    module.__path__ = list(spec.submodule_search_locations)
    module.__package__ = name
    module.__spec__ = spec
    sys.modules[name] = module
    return module


def import_only(package: str, names: dict[str, str]) -> types.ModuleType:
    stub = package_without_init(package)
    for name, submodule in names.items():
        module = importlib.import_module(f"{package}.{submodule}")
        setattr(stub, name, getattr(module, name))
    return stub


def lean_earth2studio(model_name: str) -> type:
    import_only("earth2studio.data", DATA_NAMES)
    models = import_only("earth2studio.models.px", {model_name: model_name.lower()})
    return getattr(models, model_name)
