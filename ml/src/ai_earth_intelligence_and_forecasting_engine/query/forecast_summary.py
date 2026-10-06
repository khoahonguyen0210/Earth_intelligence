from __future__ import annotations

from typing import Any

TOP_CELLS = 5
TOP_FEATURES = 5
PROBABILITY_DECIMALS = 4


def _rounded(value: float) -> float:
    return round(value, PROBABILITY_DECIMALS)


def _cell_summary(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature["properties"]
    return {
        "tile_id": properties["tile_id"],
        "centroid_lat": properties["centroid_lat"],
        "centroid_lon": properties["centroid_lon"],
        "probability": _rounded(properties["probability"]),
        "top_drivers": properties.get("top_drivers", []),
    }


def summarize_forecast_result(
    forecast_id: str, result: dict[str, Any]
) -> dict[str, Any]:
    features = result["grid"]["features"]
    probabilities = [feature["properties"]["probability"] for feature in features]
    ranked = sorted(
        features, key=lambda feature: feature["properties"]["probability"], reverse=True
    )
    explanation = result.get("explanation")

    return {
        "forecast_id": forecast_id,
        "model_version": result["model_version"],
        "data_cutoff": result["data_cutoff"],
        "forecast_window": result["forecast_window"],
        "cell_count": len(features),
        "max_probability": _rounded(max(probabilities)) if probabilities else None,
        "mean_probability": (
            _rounded(sum(probabilities) / len(probabilities)) if probabilities else None
        ),
        "top_cells": [_cell_summary(feature) for feature in ranked[:TOP_CELLS]],
        "drivers": explanation["importance"][:TOP_FEATURES] if explanation else [],
        "explanation_units": explanation["units"] if explanation else None,
    }
