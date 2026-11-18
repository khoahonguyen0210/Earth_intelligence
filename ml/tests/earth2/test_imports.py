from __future__ import annotations

import sys

import pytest

from ai_earth_intelligence_and_forecasting_engine.earth2.imports import (
    import_only,
    package_without_init,
)


@pytest.fixture
def heavy_package(tmp_path, monkeypatch):
    package = tmp_path / "heavypkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "raise RuntimeError('the package init ran')\n", encoding="utf-8"
    )
    (package / "light.py").write_text(
        "from heavypkg.helper import VALUE\n\n\nclass Light:\n    value = VALUE\n",
        encoding="utf-8",
    )
    (package / "helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (tmp_path / "plainmodule.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "heavypkg"
    for name in [
        name for name in sys.modules if name.startswith(("heavypkg", "plain"))
    ]:
        del sys.modules[name]


def test_submodules_load_without_the_package_init(heavy_package):
    stub = import_only(heavy_package, {"Light": "light"})
    assert stub.Light.value == 42
    assert "heavypkg.helper" in sys.modules
    from heavypkg import Light

    assert Light is stub.Light


def test_the_normal_import_runs_the_package_init(heavy_package):
    with pytest.raises(RuntimeError):
        __import__(heavy_package)


def test_an_imported_package_is_reused(heavy_package):
    first = package_without_init(heavy_package)
    assert package_without_init(heavy_package) is first


def test_a_plain_module_is_not_a_package(heavy_package):
    with pytest.raises(ImportError):
        package_without_init("plainmodule")
