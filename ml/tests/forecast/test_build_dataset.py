import json
from datetime import datetime, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.data.era5 import ERA5Record
from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast import build_dataset as bd

TEST_BBOX = (-120.0, 37.0, -119.9, 37.1)  # single cell
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)
TILE = CELLS[0].tile_id

# One cutoff per split, per the locked spec (Task 3.1):
#   train      2019-01-01 .. 2022-12-31
#   validation 2023-01-01 .. 2023-12-31
#   test       2024-01-01 .. 2024-12-31
TRAIN_CUTOFF = datetime(2020, 6, 1, 0, 0, tzinfo=timezone.utc)
VALIDATION_CUTOFF = datetime(2023, 6, 1, 0, 0, tzinfo=timezone.utc)
TEST_CUTOFF = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)
CUTOFFS = [TRAIN_CUTOFF, VALIDATION_CUTOFF, TEST_CUTOFF]


def _obs(observation_id: str, when: datetime) -> Observation:
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=when,
        latitude=37.05,
        longitude=-119.95,
        source_record_id=observation_id,
        ingested_at=when,
        confidence="n",
    )


def _era5(valid_time: datetime) -> ERA5Record:
    return ERA5Record(
        latitude=37.05,
        longitude=-119.95,
        valid_time=valid_time,
        temperature_2m=295.0,
        total_precipitation=0.0,
        u_wind_10m=1.0,
        v_wind_10m=1.0,
        dewpoint_2m=285.0,
    )


GEOGRAPHY = [
    GeographyCell(
        latitude=37.05,
        longitude=-119.95,
        elevation_m=800.0,
        slope_deg=12.0,
        land_cover_class=10,
    )
]

# Hand-verified fixture: a fire only in the (test_cutoff, test_cutoff+24h]
# window, so only the test-split row should be positive (target=1); the
# train/validation rows have no nearby observations at all and must be
# target=0.
OBSERVATIONS = [_obs("fire-1", TEST_CUTOFF + timedelta(hours=5))]
ERA5_RECORDS = [_era5(TEST_CUTOFF)]


def _rows():
    return bd.build_dataset(
        OBSERVATIONS, ERA5_RECORDS, GEOGRAPHY, CELLS, CUTOFFS, bbox=TEST_BBOX
    )


def test_build_dataset_produces_one_row_per_cutoff():
    rows = _rows()

    assert len(rows) == 3
    assert {row.cutoff for row in rows} == set(CUTOFFS)


def test_build_dataset_assigns_correct_split_per_cutoff():
    rows = {row.cutoff: row for row in _rows()}

    assert rows[TRAIN_CUTOFF].split == "train"
    assert rows[VALIDATION_CUTOFF].split == "validation"
    assert rows[TEST_CUTOFF].split == "test"


def test_build_dataset_target_only_positive_for_test_split():
    rows = {row.cutoff: row for row in _rows()}

    assert rows[TRAIN_CUTOFF].target == 0
    assert rows[VALIDATION_CUTOFF].target == 0
    assert rows[TEST_CUTOFF].target == 1


def test_build_dataset_environmental_features_only_present_at_test_cutoff():
    rows = {row.cutoff: row for row in _rows()}

    # No ERA5 record exists at or before the train/validation cutoffs.
    assert rows[TRAIN_CUTOFF].temperature_2m is None
    assert rows[VALIDATION_CUTOFF].temperature_2m is None
    assert rows[TEST_CUTOFF].temperature_2m == 295.0


def test_build_dataset_geography_features_present_for_every_row():
    # Static geography has no cutoff dimension, so it's attached to all
    # three rows regardless of which split they fall in.
    for row in _rows():
        assert row.elevation_m == 800.0
        assert row.slope_deg == 12.0
        assert row.land_cover_class == 10


def test_cutoff_outside_any_split_gets_unassigned_marker():
    outside_cutoff = datetime(2018, 1, 1, tzinfo=timezone.utc)

    rows = bd.build_dataset(
        [], [], [], CELLS, [outside_cutoff], bbox=TEST_BBOX
    )

    assert rows[0].split == "unassigned"


def test_manifest_row_counts_match_hand_verified_fixture():
    manifest = bd.build_dataset_manifest(_rows())

    assert manifest.row_counts == {
        "train": 1,
        "validation": 1,
        "test": 1,
        "total": 3,
    }


def test_manifest_positive_rates_match_hand_verified_fixture():
    manifest = bd.build_dataset_manifest(_rows())

    assert manifest.positive_rates["train"] == 0.0
    assert manifest.positive_rates["validation"] == 0.0
    assert manifest.positive_rates["test"] == 1.0


def test_manifest_split_dates_match_locked_spec():
    manifest = bd.build_dataset_manifest(_rows())

    assert manifest.split_dates["train"] == {
        "start": "2019-01-01",
        "end": "2022-12-31",
    }
    assert manifest.split_dates["validation"] == {
        "start": "2023-01-01",
        "end": "2023-12-31",
    }
    assert manifest.split_dates["test"] == {
        "start": "2024-01-01",
        "end": "2024-12-31",
    }


def test_manifest_feature_schema_matches_documented_columns():
    manifest = bd.build_dataset_manifest(_rows())

    assert manifest.feature_schema == list(bd.FEATURE_COLUMNS)
    assert "previous_24h_count" in manifest.feature_schema
    assert "relative_humidity" in manifest.feature_schema
    assert "elevation_m" in manifest.feature_schema


def test_manifest_versions_are_set():
    manifest = bd.build_dataset_manifest(_rows())

    assert manifest.dataset_version == bd.DATASET_VERSION
    assert manifest.feature_version == bd.FEATURE_VERSION


def test_manifest_to_dict_is_json_serializable():
    manifest = bd.build_dataset_manifest(_rows())
    payload = bd.manifest_to_dict(manifest)

    json.dumps(payload)

    assert payload["row_counts"]["total"] == 3


def test_save_dataset_roundtrip(tmp_path):
    output_path = tmp_path / "dataset.csv"
    result = bd.save_dataset(_rows(), output_path)

    content = result.read_text(encoding="utf-8")

    assert "tile_id,cutoff,split,target" in content
    assert "previous_24h_count" in content
    assert TILE in content


def test_save_dataset_manifest_roundtrip(tmp_path):
    manifest = bd.build_dataset_manifest(_rows())
    output_path = tmp_path / "manifest.json"

    bd.save_dataset_manifest(manifest, output_path)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["dataset_version"] == bd.DATASET_VERSION
    assert saved["row_counts"]["total"] == 3
