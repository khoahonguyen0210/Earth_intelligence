from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

if not torch.cuda.is_available():
    pytest.skip("needs a CUDA GPU", allow_module_level=True)

from ai_earth_intelligence_and_forecasting_engine.kernels.bench import (  # noqa: E402
    exact_index,
    within_tolerance,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.fixtures import (  # noqa: E402
    DENSE_LEVELS,
    FCN3_LEVELS,
    edge_case_columns,
    random_columns,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_compiled import (  # noqa: E402
    compiled_hot_dry_windy_index,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_cuda import (  # noqa: E402
    cuda_hot_dry_windy_index,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (  # noqa: E402
    ColumnFields,
    hot_dry_windy_index,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_triton import (  # noqa: E402
    triton_hot_dry_windy_index,
)

IMPLEMENTATIONS = {
    "eager": hot_dry_windy_index,
    "torch_compile": compiled_hot_dry_windy_index,
    "triton": triton_hot_dry_windy_index,
    "cuda": cuda_hot_dry_windy_index,
}


@pytest.mark.parametrize("name", list(IMPLEMENTATIONS))
def test_edge_cases_match_reference(name: str) -> None:
    columns = edge_case_columns(dtype=torch.float32, device="cuda")
    assert within_tolerance(IMPLEMENTATIONS[name](columns), exact_index(columns))


@pytest.mark.parametrize("name", list(IMPLEMENTATIONS))
@pytest.mark.parametrize("levels", [FCN3_LEVELS, DENSE_LEVELS])
def test_random_columns_match_reference(name: str, levels) -> None:
    columns = random_columns((3,), 37, 61, levels, seed=5, device="cuda")
    result = IMPLEMENTATIONS[name](columns)
    assert result.shape == (3, 37, 61)
    assert within_tolerance(result, exact_index(columns))


@pytest.mark.parametrize("name", list(IMPLEMENTATIONS))
def test_surface_on_a_level_boundary_matches_reference(name: str) -> None:
    columns = random_columns((2,), 4, 300, FCN3_LEVELS, seed=9, device="cuda")
    boundaries = [level * 100.0 for level in FCN3_LEVELS[:9]]
    boundaries += [(level + 50) * 100.0 for level in FCN3_LEVELS[:9]]
    pressure = columns.surface_pressure.clone()
    pressure.view(-1)[: len(boundaries)] = torch.tensor(boundaries, device="cuda")
    columns = ColumnFields(**{**columns.__dict__, "surface_pressure": pressure})
    assert within_tolerance(IMPLEMENTATIONS[name](columns), exact_index(columns))
