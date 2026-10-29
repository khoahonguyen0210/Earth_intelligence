import torch
import triton
import triton.language as tl

from ai_earth_intelligence_and_forecasting_engine.kernels import hdwi_reference as ref
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.layout import (
    PackedColumns,
    pack,
)

BLOCK = 256
LAYER_DEPTH = tl.constexpr(ref.LAYER_DEPTH_HPA)
KAPPA = tl.constexpr(ref.KAPPA)
EPSILON = tl.constexpr(ref.EPSILON)
MAGNUS_A = tl.constexpr(ref.MAGNUS_A)
MAGNUS_B = tl.constexpr(ref.MAGNUS_B)
MAGNUS_C = tl.constexpr(ref.MAGNUS_C)
KELVIN = tl.constexpr(ref.KELVIN)


@triton.jit
def _saturation(kelvin):
    celsius = kelvin - KELVIN
    return tl.exp(celsius * MAGNUS_B / (celsius + MAGNUS_C)) * MAGNUS_A


@triton.jit
def _hdwi_kernel(
    t2m_ptr,
    d2m_ptr,
    u10_ptr,
    v10_ptr,
    sp_ptr,
    t_ptr,
    q_ptr,
    u_ptr,
    v_ptr,
    pressure_ptr,
    out_ptr,
    columns,
    levels: tl.constexpr,
    block: tl.constexpr,
):
    batch = tl.program_id(1).to(tl.int64)
    offsets = tl.program_id(0) * block + tl.arange(0, block)
    inside = offsets < columns
    surface_index = batch * columns + offsets

    t2m = tl.load(t2m_ptr + surface_index, mask=inside, other=300.0)
    d2m = tl.load(d2m_ptr + surface_index, mask=inside, other=290.0)
    u10 = tl.load(u10_ptr + surface_index, mask=inside, other=0.0)
    v10 = tl.load(v10_ptr + surface_index, mask=inside, other=0.0)
    surface = tl.math.div_rn(
        tl.load(sp_ptr + surface_index, mask=inside, other=100000.0), 100.0
    )
    top = surface - LAYER_DEPTH

    wind = tl.sqrt(u10 * u10 + v10 * v10)
    deficit = _saturation(t2m) - _saturation(d2m)
    bad = (wind != wind) | (deficit != deficit) | (surface != surface)
    wind_max = wind
    deficit_max = tl.maximum(deficit, 0.0)
    active = inside

    for level in tl.static_range(levels):
        pressure = tl.load(pressure_ptr + level)
        use = active & (pressure <= surface)
        level_index = (batch * levels + level) * columns + offsets
        t = tl.load(t_ptr + level_index, mask=use, other=300.0)
        q = tl.load(q_ptr + level_index, mask=use, other=0.0)
        u = tl.load(u_ptr + level_index, mask=use, other=0.0)
        v = tl.load(v_ptr + level_index, mask=use, other=0.0)

        speed = tl.sqrt(u * u + v * v)
        lowered = t * tl.exp2(tl.log2(surface / pressure) * KAPPA)
        vapor = q * surface / (q * (1.0 - EPSILON) + EPSILON)
        level_deficit = _saturation(lowered) - vapor

        bad = bad | (use & ((speed != speed) | (level_deficit != level_deficit)))
        wind_max = tl.where(use, tl.maximum(wind_max, speed), wind_max)
        deficit_max = tl.where(
            use, tl.maximum(deficit_max, tl.maximum(level_deficit, 0.0)), deficit_max
        )
        active = tl.where(use & (pressure < top), False, active)

    result = tl.where(bad, float("nan"), wind_max * deficit_max)
    tl.store(out_ptr + surface_index, result, mask=inside)


def triton_hot_dry_windy_index(columns: ColumnFields) -> torch.Tensor:
    return launch(pack(columns))


def launch(packed: PackedColumns) -> torch.Tensor:
    t2m, d2m, u10, v10, sp = packed.surface
    t, q, u, v = packed.levels
    out = torch.empty_like(t2m)
    grid = (triton.cdiv(packed.columns, BLOCK), packed.batch)
    _hdwi_kernel[grid](
        t2m,
        d2m,
        u10,
        v10,
        sp,
        t,
        q,
        u,
        v,
        packed.pressure,
        out,
        packed.columns,
        levels=packed.pressure.numel(),
        block=BLOCK,
    )
    return out.view(packed.grid)
