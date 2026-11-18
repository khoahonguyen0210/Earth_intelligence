from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (
    build_columns,
    crop_indices,
    daily_features,
    required_variables,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import FEATURES
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import (
    LEAD_DAYS,
    daily_valid_times,
    forecast_steps,
    initialization_time,
)
from ai_earth_intelligence_and_forecasting_engine.kernels.hdwi_reference import (
    ColumnFields,
)

MEMBER_DIM = "ensemble"
NOISE_SCALE = 0.05
NOISE_SEED = 20261118
ABSOLUTE_TOLERANCE = 0.01
RELATIVE_TOLERANCE = 0.001


@dataclass(frozen=True)
class EnsembleForecast:
    cutoff: datetime
    initialization: datetime
    members: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    features: dict[str, np.ndarray]
    approximate: bool


@dataclass(frozen=True)
class BatchRecord:
    members: list[int]
    forecast_steps: int
    seconds: float
    peak_memory_gb: float
    started_at: float
    finished_at: float

    @property
    def member_steps(self) -> int:
        return len(self.members) * self.forecast_steps


def split_members(members: int, workers: int) -> list[list[int]]:
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if members < workers:
        raise ValueError("each worker needs at least one member")
    size, extra = divmod(members, workers)
    groups = []
    start = 0
    for worker in range(workers):
        count = size + (1 if worker < extra else 0)
        groups.append(list(range(start, start + count)))
        start += count
    return groups


def member_noise(
    shape: torch.Size, member: int, seed: int, device: torch.device, dtype: torch.dtype
) -> torch.Tensor:
    generator = torch.Generator(device=device).manual_seed(seed + member)
    return torch.randn(shape, generator=generator, device=device, dtype=dtype)


def perturb(
    x: torch.Tensor,
    members: list[int],
    scale: float = NOISE_SCALE,
    seed: int = NOISE_SEED,
) -> torch.Tensor:
    spread = x.std(dim=(-2, -1), keepdim=True)
    batch = x.unsqueeze(0).repeat(len(members), *([1] * x.dim()))
    for position, member in enumerate(members):
        if member:
            noise = member_noise(x.shape, member, seed, x.device, x.dtype)
            batch[position] += scale * spread * noise
    return batch


def member_columns(
    output: torch.Tensor,
    coords: dict[str, np.ndarray],
    rows: np.ndarray,
    columns: np.ndarray,
) -> tuple[ColumnFields, bool]:
    dims = list(coords)
    if dims[0] != MEMBER_DIM:
        raise ValueError(f"model output must start with the {MEMBER_DIM} dimension")
    keep = (MEMBER_DIM, "variable", "lat", "lon")
    grid = output[tuple(slice(None) if dim in keep else -1 for dim in dims)]
    grid = grid.index_select(-2, torch.as_tensor(rows, device=grid.device))
    grid = grid.index_select(-1, torch.as_tensor(columns, device=grid.device))
    variables = [str(name) for name in coords["variable"]]
    fields = {
        name: grid[:, variables.index(name)].double()
        for name in required_variables() + ["d2m"]
        if name in variables
    }
    return build_columns(fields)


def run_members(
    model: Any,
    x: torch.Tensor,
    x_coords: dict[str, np.ndarray],
    cutoff: datetime,
    members: list[int],
    batch_size: int,
    device: str = "cuda",
    scale: float = NOISE_SCALE,
    seed: int = NOISE_SEED,
) -> tuple[EnsembleForecast, list[BatchRecord]]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    initialization = initialization_time(cutoff)
    lead_by_time = {
        valid: lead for lead in LEAD_DAYS for valid in daily_valid_times(cutoff, lead)
    }
    steps = forecast_steps(cutoff)
    cuda = torch.device(device).type == "cuda"
    state = x.to(device)
    collected: dict[str, list[np.ndarray]] = {name: [] for name in FEATURES}
    records = []
    approximate = False
    latitude = longitude = np.empty(0)

    for start in range(0, len(members), batch_size):
        chosen = [int(member) for member in members[start : start + batch_size]]
        if cuda:
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
        started_at = time.time()
        started = time.perf_counter()
        coords = OrderedDict({MEMBER_DIM: np.array(chosen)}) | OrderedDict(x_coords)
        snapshots: dict[int, list[ColumnFields]] = {lead: [] for lead in LEAD_DAYS}
        with torch.inference_mode():
            iterator = model.create_iterator(
                perturb(state, chosen, scale, seed), coords
            )
            for _ in range(steps + 1):
                output, output_coords = next(iterator)
                hours = int(output_coords["lead_time"][-1] / np.timedelta64(1, "h"))
                valid = initialization + timedelta(hours=hours)
                if valid in lead_by_time:
                    rows, cols = crop_indices(
                        output_coords["lat"], output_coords["lon"]
                    )
                    latitude = output_coords["lat"][rows]
                    longitude = output_coords["lon"][cols]
                    fields, approximate = member_columns(
                        output, output_coords, rows, cols
                    )
                    snapshots[lead_by_time[valid]].append(fields)
                del output
            del iterator
            by_lead = [daily_features(snapshots[lead]) for lead in LEAD_DAYS]
        for name in FEATURES:
            stacked = torch.stack([day[name] for day in by_lead], dim=1)
            collected[name].append(stacked.cpu().numpy())
        if cuda:
            torch.cuda.synchronize()
        records.append(
            BatchRecord(
                members=chosen,
                forecast_steps=steps,
                seconds=time.perf_counter() - started,
                peak_memory_gb=(
                    torch.cuda.max_memory_allocated() / 1e9 if cuda else 0.0
                ),
                started_at=started_at,
                finished_at=time.time(),
            )
        )

    forecast = EnsembleForecast(
        cutoff=cutoff,
        initialization=initialization,
        members=np.array(members, dtype=np.int64),
        latitude=np.asarray(latitude, dtype=np.float64),
        longitude=np.asarray(longitude, dtype=np.float64),
        features={name: np.concatenate(collected[name]) for name in FEATURES},
        approximate=approximate,
    )
    return forecast, records


def warm_throughput(records: list[BatchRecord]) -> float:
    warm = records[1:] or records
    return sum(record.member_steps for record in warm) / sum(
        record.seconds for record in warm
    )


def merge_ensembles(parts: list[EnsembleForecast]) -> EnsembleForecast:
    if not parts:
        raise ValueError("nothing to merge")
    members = np.concatenate([part.members for part in parts])
    order = np.argsort(members)
    first = parts[0]
    return EnsembleForecast(
        cutoff=first.cutoff,
        initialization=first.initialization,
        members=members[order],
        latitude=first.latitude,
        longitude=first.longitude,
        features={
            name: np.concatenate([part.features[name] for part in parts])[order]
            for name in FEATURES
        },
        approximate=all(part.approximate for part in parts),
    )


def save_ensemble(forecast: EnsembleForecast, path: Path) -> None:
    arrays: dict[str, Any] = {
        "cutoff": np.array(forecast.cutoff.isoformat()),
        "initialization": np.array(forecast.initialization.isoformat()),
        "members": forecast.members,
        "latitude": forecast.latitude,
        "longitude": forecast.longitude,
        "approximate": np.array(forecast.approximate),
        **forecast.features,
    }
    np.savez_compressed(path, **arrays)


def load_ensemble(path: Path) -> EnsembleForecast:
    with np.load(path) as data:
        return EnsembleForecast(
            cutoff=datetime.fromisoformat(str(data["cutoff"])),
            initialization=datetime.fromisoformat(str(data["initialization"])),
            members=data["members"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            features={name: data[name] for name in FEATURES},
            approximate=bool(data["approximate"]),
        )


def agreement(values: np.ndarray, reference: np.ndarray) -> dict[str, Any]:
    same_missing = bool(np.array_equal(np.isnan(values), np.isnan(reference)))
    present = ~np.isnan(reference)
    difference = np.abs(values[present] - reference[present])
    limit = ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * np.abs(reference[present])
    return {
        "identical": same_missing and bool(np.all(difference == 0)),
        "within_tolerance": same_missing and bool(np.all(difference <= limit)),
        "largest_error_over_limit": (
            round(float(np.max(difference / limit)), 4) if difference.size else 0.0
        ),
    }


def spread_by_lead(forecast: EnsembleForecast, name: str = "hdw_max") -> list[float]:
    values = forecast.features[name]
    if values.shape[0] < 2:
        return [0.0 for _ in LEAD_DAYS]
    spread = np.nanstd(values, axis=0)
    return [
        round(float(np.nanmedian(spread[lead])), 4) for lead in range(len(LEAD_DAYS))
    ]
