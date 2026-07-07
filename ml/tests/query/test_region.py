import pytest

from ai_earth_intelligence_and_forecasting_engine.data.grid import CALIFORNIA_BBOX
from ai_earth_intelligence_and_forecasting_engine.query.region import (
    NAMED_REGIONS,
    normalize_region,
)
from ai_earth_intelligence_and_forecasting_engine.query.schema import RegionSpec


def test_normalize_bbox_region():
    region = RegionSpec(kind="bbox", value=(-124.5, 32.5, -114.0, 42.0))

    result = normalize_region(region)

    assert result.bbox == (-124.5, 32.5, -114.0, 42.0)
    assert result.source_kind == "bbox"
    assert result.geometry["type"] == "Polygon"
    assert result.geometry["coordinates"][0][0] == [-124.5, 32.5]


def test_normalize_bbox_region_rejects_wrong_length():
    region = RegionSpec(kind="bbox", value=(-124.5, 32.5, -114.0))

    with pytest.raises(ValueError, match="4 floats"):
        normalize_region(region)


def test_normalize_bbox_region_rejects_inverted_bbox():
    region = RegionSpec(kind="bbox", value=(-114.0, 32.5, -124.5, 42.0))

    with pytest.raises(ValueError, match="degenerate or inverted"):
        normalize_region(region)


def test_normalize_coordinates_region_snaps_to_grid_cell():
    region = RegionSpec(kind="coordinates", value=(37.55, -119.95))

    result = normalize_region(region)

    assert result.source_kind == "coordinates"
    assert result.label == "CA_0050_0045"
    assert result.bbox == (-120.0, 37.5, -119.9, 37.6)
    assert result.geometry["type"] == "Polygon"


def test_normalize_coordinates_region_outside_grid_raises():
    region = RegionSpec(kind="coordinates", value=(50.0, -119.5))

    with pytest.raises(ValueError, match="outside the supported California grid"):
        normalize_region(region)


def test_normalize_coordinates_region_rejects_wrong_length():
    region = RegionSpec(kind="coordinates", value=(37.5,))

    with pytest.raises(ValueError, match="latitude, longitude"):
        normalize_region(region)


def test_normalize_named_region_california():
    region = RegionSpec(kind="named", value="California")

    result = normalize_region(region)

    assert result.bbox == CALIFORNIA_BBOX
    assert result.source_kind == "named"
    assert result.label == "california"


def test_normalize_named_region_is_case_and_space_insensitive():
    region = RegionSpec(kind="named", value="  Bay Area  ")

    result = normalize_region(region)

    assert result.label == "bay_area"
    assert result.bbox == NAMED_REGIONS["bay_area"]


def test_normalize_named_region_rejects_unsupported_name():
    region = RegionSpec(kind="named", value="Atlantis")

    with pytest.raises(ValueError, match="Unsupported named region"):
        normalize_region(region)


def test_normalize_region_rejects_unknown_kind():
    region = RegionSpec(kind="polygon", value="whatever")

    with pytest.raises(ValueError, match="Unsupported region kind"):
        normalize_region(region)


def test_normalize_region_is_deterministic():
    region = RegionSpec(kind="named", value="california")

    first = normalize_region(region)
    second = normalize_region(region)

    assert first == second


@pytest.mark.parametrize("name", sorted(NAMED_REGIONS))
def test_all_named_regions_normalize_without_error(name):
    region = RegionSpec(kind="named", value=name)

    result = normalize_region(region)

    west, south, east, north = result.bbox
    assert west < east
    assert south < north
