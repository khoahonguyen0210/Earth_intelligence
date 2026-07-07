from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.data.grid import is_valid_polygon
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.query.map_result import (
    build_map_feature,
    build_map_result,
    build_regional_map_result,
    map_value_from_count,
)
from ai_earth_intelligence_and_forecasting_engine.query.region import normalize_region
from ai_earth_intelligence_and_forecasting_engine.query.schema import (
    RegionSpec,
    TimeRangeSpec,
)
from ai_earth_intelligence_and_forecasting_engine.query.time_range import (
    normalize_time_range,
)

REGION_A = normalize_region(RegionSpec(kind="named", value="bay_area"))
REGION_B = normalize_region(RegionSpec(kind="named", value="central_valley"))
TIME_RANGE = normalize_time_range(
    TimeRangeSpec(start="2024-08-01", end="2024-08-07")
)


def _obs(observation_id: str, latitude: float, longitude: float) -> Observation:
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=datetime(2024, 8, 3, 10, 0, tzinfo=timezone.utc),
        latitude=latitude,
        longitude=longitude,
        source_record_id=observation_id,
        ingested_at=datetime(2024, 8, 4, tzinfo=timezone.utc),
    )


def test_build_map_feature_has_geometry_value_time_units():
    map_value = map_value_from_count(
        region=REGION_A, time_range=TIME_RANGE, value=5, units="fire_count"
    )

    feature = build_map_feature(map_value)

    assert feature["type"] == "Feature"
    assert feature["geometry"] == REGION_A.geometry
    assert is_valid_polygon(feature["geometry"])
    assert feature["properties"]["value"] == 5
    assert feature["properties"]["units"] == "fire_count"
    assert feature["properties"]["time"] == {
        "start": TIME_RANGE.start.isoformat(),
        "end": TIME_RANGE.end.isoformat(),
    }
    assert feature["properties"]["region_kind"] == "named"
    assert feature["properties"]["region_label"] == "bay_area"


def test_build_map_result_wraps_features_in_feature_collection():
    values = [
        map_value_from_count(REGION_A, TIME_RANGE, 5),
        map_value_from_count(REGION_B, TIME_RANGE, 12),
    ]

    result = build_map_result(values)

    assert result["type"] == "FeatureCollection"
    assert len(result["features"]) == 2
    assert result["features"][0]["properties"]["value"] == 5
    assert result["features"][1]["properties"]["value"] == 12


def test_build_map_result_empty_list_is_valid_empty_collection():
    result = build_map_result([])

    assert result == {"type": "FeatureCollection", "features": []}


def test_build_regional_map_result_computes_real_counts():
    # Bay Area and Central Valley bboxes overlap near their shared edge, so
    # these points are deliberately chosen from the *non-overlapping* part
    # of each region: the far-west edge of Bay Area (west of Central
    # Valley's western bound), and the center of Central Valley (east of
    # Bay Area's eastern bound).
    only_in_bay_area = (37.9, -123.2)
    only_in_central_valley = (37.5, -120.5)

    observations = [
        _obs("1", *only_in_bay_area),
        _obs("2", *only_in_bay_area),
        _obs("3", 0.0, 0.0),  # far from both regions, excluded from both
    ]

    result = build_regional_map_result(
        observations, [REGION_A, REGION_B], TIME_RANGE
    )

    assert result["type"] == "FeatureCollection"
    values_by_label = {
        feature["properties"]["region_label"]: feature["properties"]["value"]
        for feature in result["features"]
    }

    assert values_by_label["bay_area"] == 2
    assert values_by_label["central_valley"] == 0

    observations.append(_obs("4", *only_in_central_valley))
    result = build_regional_map_result(
        observations, [REGION_A, REGION_B], TIME_RANGE
    )
    values_by_label = {
        feature["properties"]["region_label"]: feature["properties"]["value"]
        for feature in result["features"]
    }

    assert values_by_label["bay_area"] == 2
    assert values_by_label["central_valley"] == 1


def test_build_regional_map_result_default_units():
    result = build_regional_map_result([], [REGION_A], TIME_RANGE)

    assert result["features"][0]["properties"]["units"] == "fire_count"
