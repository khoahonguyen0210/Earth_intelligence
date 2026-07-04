import json
from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
    GridConfig,
    build_california_grid,
    build_grid_metadata,
    build_tile_id,
    cells_to_geojson,
    is_valid_polygon,
    save_grid_geojson,
    save_grid_metadata,
)


def test_grid_config_defaults():
    config = GridConfig()

    assert config.bbox == CALIFORNIA_BBOX
    assert config.resolution_deg == 0.1
    assert config.version == "v1"


def test_build_tile_id_is_zero_padded_and_stable():
    assert build_tile_id(0, 0) == "CA_0000_0000"
    assert build_tile_id(94, 104) == "CA_0094_0104"


def test_build_california_grid_cell_count_matches_bbox():
    cells = build_california_grid()

    west, south, east, north = CALIFORNIA_BBOX
    expected_width = round((east - west) / GRID_RESOLUTION_DEG)
    expected_height = round((north - south) / GRID_RESOLUTION_DEG)

    assert len(cells) == expected_width * expected_height
    assert len(cells) == 9975


def test_build_california_grid_is_deterministic():
    first_run = build_california_grid()
    second_run = build_california_grid()

    assert first_run == second_run


def test_build_california_grid_has_no_duplicate_ids():
    cells = build_california_grid()
    tile_ids = [cell.tile_id for cell in cells]

    assert len(tile_ids) == len(set(tile_ids))


def test_build_california_grid_all_polygons_valid():
    cells = build_california_grid()

    assert all(is_valid_polygon(cell.geometry) for cell in cells)


def test_build_california_grid_respects_bbox_edges():
    cells = build_california_grid()

    west, south, east, north = CALIFORNIA_BBOX

    min_lon = min(cell.min_lon for cell in cells)
    max_lon = max(cell.max_lon for cell in cells)
    min_lat = min(cell.min_lat for cell in cells)
    max_lat = max(cell.max_lat for cell in cells)

    assert min_lon == west
    assert max_lon == east
    assert min_lat == south
    assert max_lat == north


def test_build_california_grid_centroid_is_cell_midpoint():
    cells = build_california_grid()
    cell = cells[0]

    assert cell.centroid_lon == (cell.min_lon + cell.max_lon) / 2
    assert cell.centroid_lat == (cell.min_lat + cell.max_lat) / 2


def test_is_valid_polygon_rejects_unclosed_ring():
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
    }

    assert is_valid_polygon(geometry) is False


def test_is_valid_polygon_rejects_degenerate_zero_area():
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]],
    }

    assert is_valid_polygon(geometry) is False


def test_is_valid_polygon_rejects_non_polygon_type():
    assert is_valid_polygon({"type": "Point", "coordinates": [0, 0]}) is False


def test_cells_to_geojson_structure():
    cells = build_california_grid(
        bbox=(-120.0, 37.0, -119.8, 37.2), resolution_deg=0.1
    )

    geojson = cells_to_geojson(cells)

    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 4

    feature = geojson["features"][0]

    assert feature["type"] == "Feature"
    assert feature["properties"]["tile_id"] == feature["id"]


def test_save_grid_geojson_roundtrip(tmp_path):
    cells = build_california_grid(
        bbox=(-120.0, 37.0, -119.9, 37.1), resolution_deg=0.1
    )

    output_path = tmp_path / "grid.geojson"
    result = save_grid_geojson(cells, output_path)

    saved = json.loads(result.read_text(encoding="utf-8"))

    assert saved["type"] == "FeatureCollection"
    assert len(saved["features"]) == 1


def test_build_grid_metadata_fields():
    created_at = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    metadata = build_grid_metadata(
        bbox=CALIFORNIA_BBOX,
        resolution_deg=GRID_RESOLUTION_DEG,
        version="v1",
        cell_count=9975,
        created_at=created_at,
    )

    assert metadata["grid_version"] == "v1"
    assert metadata["cell_count"] == 9975
    assert metadata["bbox"] == list(CALIFORNIA_BBOX)
    assert metadata["created_at"] == "2026-09-20T00:00:00+00:00"
    assert "boundary_rule" in metadata


def test_save_grid_metadata_roundtrip(tmp_path):
    metadata = build_grid_metadata(
        bbox=CALIFORNIA_BBOX,
        resolution_deg=GRID_RESOLUTION_DEG,
        version="v1",
        cell_count=9975,
        created_at=datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc),
    )

    output_path = tmp_path / "metadata.json"
    save_grid_metadata(metadata, output_path)

    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["grid_version"] == "v1"
