from __future__ import annotations

from dataclasses import dataclass, fields

import torch

LAYER_DEPTH_HPA = 50.0
KAPPA = 0.2857
EPSILON = 0.622
MAGNUS_A = 6.1094
MAGNUS_B = 17.625
MAGNUS_C = 243.04
KELVIN = 273.15


@dataclass(frozen=True)
class ColumnFields:
    t2m: torch.Tensor
    d2m: torch.Tensor
    u10: torch.Tensor
    v10: torch.Tensor
    surface_pressure: torch.Tensor
    temperature: torch.Tensor
    specific_humidity: torch.Tensor
    u: torch.Tensor
    v: torch.Tensor
    pressure: torch.Tensor

    def to(self, device: torch.device | str, dtype: torch.dtype) -> ColumnFields:
        return ColumnFields(
            **{
                item.name: getattr(self, item.name).to(device=device, dtype=dtype)
                for item in fields(self)
            }
        )


def validate(columns: ColumnFields) -> None:
    surface = columns.t2m.shape
    if len(surface) < 2:
        raise ValueError("surface fields need at least two grid dimensions")
    for name in ("d2m", "u10", "v10", "surface_pressure"):
        if getattr(columns, name).shape != surface:
            raise ValueError(f"{name} must have shape {tuple(surface)}")

    pressure = columns.pressure
    if pressure.ndim != 1 or pressure.numel() == 0:
        raise ValueError("pressure must be a non-empty 1-D tensor of levels in hPa")
    if pressure.numel() > 1 and not bool(torch.all(pressure[:-1] > pressure[1:])):
        raise ValueError("pressure levels must be strictly descending")

    levels = (*surface[:-2], pressure.numel(), *surface[-2:])
    for name in ("temperature", "specific_humidity", "u", "v"):
        if getattr(columns, name).shape != levels:
            raise ValueError(f"{name} must have shape {levels}")


def saturation_vapor_pressure(temperature: torch.Tensor) -> torch.Tensor:
    celsius = temperature - KELVIN
    return MAGNUS_A * torch.exp(MAGNUS_B * celsius / (MAGNUS_C + celsius))


def vapor_pressure(
    specific_humidity: torch.Tensor, pressure_hpa: torch.Tensor
) -> torch.Tensor:
    return (
        specific_humidity
        * pressure_hpa
        / (EPSILON + (1.0 - EPSILON) * specific_humidity)
    )


def surface_vpd(t2m: torch.Tensor, d2m: torch.Tensor) -> torch.Tensor:
    deficit = saturation_vapor_pressure(t2m) - saturation_vapor_pressure(d2m)
    return torch.clamp(deficit, min=0.0)


def surface_vpd_from_relative_humidity(
    t2m: torch.Tensor, relative_humidity: torch.Tensor
) -> torch.Tensor:
    deficit = saturation_vapor_pressure(t2m) * (1.0 - relative_humidity / 100.0)
    return torch.clamp(deficit, min=0.0)


def adjusted_vpd(
    temperature: torch.Tensor,
    specific_humidity: torch.Tensor,
    pressure_hpa: torch.Tensor,
    surface_hpa: torch.Tensor,
) -> torch.Tensor:
    lowered = temperature * (surface_hpa / pressure_hpa) ** KAPPA
    deficit = saturation_vapor_pressure(lowered) - vapor_pressure(
        specific_humidity, surface_hpa
    )
    return torch.clamp(deficit, min=0.0)


def layer_mask(pressure_hpa: torch.Tensor, surface_hpa: torch.Tensor) -> torch.Tensor:
    levels = pressure_hpa.view(-1, 1, 1)
    surface = surface_hpa.unsqueeze(-3)
    above_ground = levels <= surface
    within = levels >= surface - LAYER_DEPTH_HPA
    first_beyond = within.sum(dim=-3, keepdim=True)
    index = torch.arange(pressure_hpa.numel(), device=pressure_hpa.device).view(
        -1, 1, 1
    )
    return above_ground & (within | (index == first_beyond))


def _masked_max(values: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    floor = torch.full_like(values, float("-inf"))
    return torch.amax(torch.where(mask, values, floor), dim=-3)


def hot_dry_windy_index(columns: ColumnFields) -> torch.Tensor:
    validate(columns)
    return compute_index(columns)


def compute_index(columns: ColumnFields) -> torch.Tensor:
    surface_hpa = columns.surface_pressure / 100.0
    pressure = columns.pressure.view(-1, 1, 1)
    mask = layer_mask(columns.pressure, surface_hpa)

    level_wind = torch.sqrt(columns.u**2 + columns.v**2)
    level_vpd = adjusted_vpd(
        columns.temperature,
        columns.specific_humidity,
        pressure,
        surface_hpa.unsqueeze(-3),
    )

    wind = torch.maximum(
        torch.sqrt(columns.u10**2 + columns.v10**2), _masked_max(level_wind, mask)
    )
    vpd = torch.maximum(
        surface_vpd(columns.t2m, columns.d2m), _masked_max(level_vpd, mask)
    )
    index = wind * vpd
    return torch.where(torch.isnan(surface_hpa), surface_hpa, index)


def surface_hot_dry_windy_index(
    t2m: torch.Tensor, d2m: torch.Tensor, u10: torch.Tensor, v10: torch.Tensor
) -> torch.Tensor:
    return torch.sqrt(u10**2 + v10**2) * surface_vpd(t2m, d2m)
