from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.query.region import NormalizedRegion
from ai_earth_intelligence_and_forecasting_engine.query.statistics import count
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    NormalizedTimeRange,
)


@dataclass(frozen=True)
class MapValue:
    region: NormalizedRegion
    value: float
    time_range: NormalizedTimeRange
    units: str


def map_value_from_count(
    region: NormalizedRegion,
    time_range: NormalizedTimeRange,
    value: float,
    units: str = "count",
) -> MapValue:
    return MapValue(region=region, value=value, time_range=time_range, units=units)


def build_map_feature(map_value: MapValue) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": map_value.region.geometry,
        "properties": {
            "value": map_value.value,
            "time": {
                "start": map_value.time_range.start.isoformat(),
                "end": map_value.time_range.end.isoformat(),
            },
            "units": map_value.units,
            "region_kind": map_value.region.source_kind,
            "region_label": map_value.region.label,
        },
    }


def build_map_result(map_values: list[MapValue]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [build_map_feature(map_value) for map_value in map_values],
    }


def build_regional_map_result(
    observations: list[Observation],
    regions: list[NormalizedRegion],
    time_range: NormalizedTimeRange,
    units: str = "fire_count",
) -> dict[str, Any]:
    map_values = [
        map_value_from_count(
            region=region,
            time_range=time_range,
            value=count(observations, region, time_range),
            units=units,
        )
        for region in regions
    ]

    return build_map_result(map_values)
