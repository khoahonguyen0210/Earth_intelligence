import json
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ai_earth_intelligence_and_forecasting_engine.data.geography import (
    GeographyConfig,
    build_geography_grid,
    build_provenance,
    compute_slope_degrees,
    dem_tile_url,
    fetch_dem_sample,
    fetch_landcover_sample,
    save_geography_records,
    save_provenance,
    worldcover_tile_url,
)


def test_geography_config_default_resolution():
    config = GeographyConfig()

    assert config.grid_resolution_deg == 0.1


def test_dem_tile_url_positive_lat_negative_lon():
    url = dem_tile_url(37.4, -119.6)

    assert url == (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N37_00_W120_00_DEM/"
        "Copernicus_DSM_COG_10_N37_00_W120_00_DEM.tif"
    )


def test_dem_tile_url_boundary_floors_toward_tile_origin():
    url = dem_tile_url(37.99, -120.01)

    assert "N37_00_W121_00" in url


def test_worldcover_tile_url_aligns_to_three_degree_grid():
    url = worldcover_tile_url(37.4, -119.6)

    assert url == (
        "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
        "ESA_WorldCover_10m_2021_v200_N36W120_Map.tif"
    )


def test_compute_slope_degrees_flat_surface_is_zero():
    elevation = np.full((5, 5), 100.0)

    slope = compute_slope_degrees(elevation, pixel_size_x_m=30.0, pixel_size_y_m=30.0)

    assert np.allclose(slope, 0.0)


def test_compute_slope_degrees_known_ramp():
    elevation = np.array(
        [[0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0]]
    )

    slope = compute_slope_degrees(elevation, pixel_size_x_m=1.0, pixel_size_y_m=1.0)

    assert np.allclose(slope[:, 1:3], 45.0)


def _write_test_raster(path, array, transform, dtype, nodata=None) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype=dtype,
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(array, 1)


def test_build_geography_grid_single_cell(tmp_path):
    bbox = (-120.0, 37.0, -119.9, 37.1)

    dem_path = tmp_path / "dem.tif"
    landcover_path = tmp_path / "landcover.tif"

    dem_transform = from_origin(-120.0, 37.1, 0.025, 0.025)
    elevation = np.full((4, 4), 500.0, dtype="float64")
    _write_test_raster(dem_path, elevation, dem_transform, "float64")

    landcover_transform = from_origin(-120.0, 37.1, 0.025, 0.025)
    land_cover = np.full((4, 4), 40, dtype="uint8")
    _write_test_raster(landcover_path, land_cover, landcover_transform, "uint8")

    records = build_geography_grid(
        bbox=bbox,
        resolution_deg=0.1,
        dem_path=dem_path,
        landcover_path=landcover_path,
    )

    assert len(records) == 1

    record = records[0]

    assert record.latitude == pytest.approx(37.05)
    assert record.longitude == pytest.approx(-119.95)
    assert record.elevation_m == pytest.approx(500.0)
    assert record.slope_deg == pytest.approx(0.0)
    assert record.land_cover_class == 40


def test_fetch_dem_sample_windows_remote_tile(tmp_path):
    source_path = tmp_path / "source_dem.tif"
    output_path = tmp_path / "dem_sample.tif"

    transform = from_origin(-120.0, 38.0, 0.01, 0.01)
    elevation = np.arange(100 * 100, dtype="float64").reshape(100, 100)
    _write_test_raster(source_path, elevation, transform, "float64")

    bbox = (-119.9, 37.8, -119.8, 37.9)
    real_open = rasterio.open

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/vsicurl/"):
            return real_open(source_path, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.geography.rasterio.open",
        side_effect=fake_open,
    ):
        result = fetch_dem_sample(bbox=bbox, output_path=output_path)

    assert result == output_path
    assert output_path.exists()

    with rasterio.open(output_path) as dst:
        assert dst.width > 0
        assert dst.height > 0
        assert dst.bounds.left >= bbox[0] - 0.02
        assert dst.bounds.right <= bbox[2] + 0.02


def test_fetch_landcover_sample_windows_remote_tile(tmp_path):
    source_path = tmp_path / "source_landcover.tif"
    output_path = tmp_path / "landcover_sample.tif"

    transform = from_origin(-120.0, 39.0, 0.01, 0.01)
    land_cover = np.full((300, 300), 30, dtype="uint8")
    _write_test_raster(source_path, land_cover, transform, "uint8")

    bbox = (-119.9, 37.8, -119.8, 37.9)
    real_open = rasterio.open

    def fake_open(path, *args, **kwargs):
        if str(path).startswith("/vsicurl/"):
            return real_open(source_path, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    with patch(
        "ai_earth_intelligence_and_forecasting_engine.data.geography.rasterio.open",
        side_effect=fake_open,
    ):
        result = fetch_landcover_sample(bbox=bbox, output_path=output_path)

    assert result == output_path
    assert output_path.exists()


def test_save_geography_records_writes_csv(tmp_path):
    from ai_earth_intelligence_and_forecasting_engine.data.geography import (
        GeographyCell,
    )

    records = [
        GeographyCell(
            latitude=37.05,
            longitude=-119.95,
            elevation_m=500.0,
            slope_deg=1.5,
            land_cover_class=40,
        )
    ]

    output_path = tmp_path / "geography.csv"
    result = save_geography_records(records, output_path)

    content = result.read_text(encoding="utf-8")

    assert "latitude,longitude,elevation_m,slope_deg,land_cover_class" in content
    assert "37.05,-119.95,500.0,1.5,40" in content


def test_build_and_save_provenance(tmp_path):
    retrieved_at = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    provenance = build_provenance(
        bbox=(-120.0, 37.0, -119.6, 37.4),
        resolution_deg=0.1,
        dem_url="https://example.test/dem.tif",
        landcover_url="https://example.test/landcover.tif",
        retrieved_at=retrieved_at,
    )

    output_path = tmp_path / "provenance.json"
    save_provenance(provenance, output_path)

    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["dem_source"] == "Copernicus DEM GLO-30"
    assert saved["landcover_source"] == "ESA WorldCover 10m v200 2021"
    assert saved["bbox"] == [-120.0, 37.0, -119.6, 37.4]
    assert saved["retrieved_at"] == "2026-09-20T00:00:00+00:00"
