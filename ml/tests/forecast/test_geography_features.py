from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.forecast import (
    geography_features as gf,
)

TEST_BBOX = (-120.0, 37.0, -119.8, 37.2)
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)


def _geo_cell(
    latitude: float = 37.05,
    longitude: float = -119.95,
    elevation_m: float = 500.0,
    slope_deg: float = 10.0,
    land_cover_class: int = 10,
) -> GeographyCell:
    return GeographyCell(
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        slope_deg=slope_deg,
        land_cover_class=land_cover_class,
    )


def _features(geography_cells, cells=CELLS, bbox=TEST_BBOX):
    return gf.compute_geography_features(geography_cells, cells, bbox=bbox)


def _by_tile(records, tile_id):
    return next(r for r in records if r.tile_id == tile_id)


def test_attaches_elevation_slope_landcover_to_matching_tile():
    geo_cell = _geo_cell(elevation_m=1200.0, slope_deg=15.5, land_cover_class=20)

    records = _features([geo_cell])
    result = _by_tile(records, CELLS[0].tile_id)

    assert result.elevation_m == 1200.0
    assert result.slope_deg == 15.5
    assert result.land_cover_class == 20


def test_missing_geography_data_produces_none_values():
    records = _features([])
    result = _by_tile(records, CELLS[0].tile_id)

    assert result.elevation_m is None
    assert result.slope_deg is None
    assert result.land_cover_class is None


def test_nan_elevation_treated_as_missing():
    geo_cell = _geo_cell(elevation_m=float("nan"))

    records = _features([geo_cell])
    result = _by_tile(records, CELLS[0].tile_id)

    assert result.elevation_m is None
    assert result.slope_deg is None
    assert result.land_cover_class is None


def test_geography_cell_outside_any_tile_is_ignored():
    geo_cell = _geo_cell(latitude=10.0, longitude=10.0)

    records = _features([geo_cell])

    assert all(r.elevation_m is None for r in records)


def test_multiple_geography_cells_map_to_different_tiles():
    cell_sw = _geo_cell(latitude=37.05, longitude=-119.95, elevation_m=100.0)
    cell_ne = _geo_cell(latitude=37.15, longitude=-119.85, elevation_m=2000.0)

    records = _features([cell_sw, cell_ne])

    elevations = sorted(r.elevation_m for r in records if r.elevation_m is not None)
    assert elevations == [100.0, 2000.0]


def test_compute_geography_features_one_record_per_cell_no_cutoff_dimension():
    records = _features([])

    assert len(records) == len(CELLS)
    tile_ids = {r.tile_id for r in records}
    assert tile_ids == {cell.tile_id for cell in CELLS}


def test_save_geography_features_roundtrip(tmp_path):
    geo_cell = _geo_cell()
    records = _features([geo_cell])

    output_path = tmp_path / "geo_features.csv"
    result = gf.save_geography_features(records, output_path)

    content = result.read_text(encoding="utf-8")

    assert "elevation_m,slope_deg,land_cover_class" in content
    assert CELLS[0].tile_id in content
