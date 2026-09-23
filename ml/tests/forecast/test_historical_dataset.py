from datetime import date, datetime, timedelta, timezone

from ai_earth_intelligence_and_forecasting_engine.data.era5 import ERA5Record
from ai_earth_intelligence_and_forecasting_engine.data.geography import GeographyCell
from ai_earth_intelligence_and_forecasting_engine.data.grid import (
    build_california_grid,
)
from ai_earth_intelligence_and_forecasting_engine.data.history import (
    FIRMS_MAX_DAY_RANGE,
    FIRMSSpan,
    firms_spans,
    historical_cutoffs,
    observation_window,
    parse_span_file_name,
    required_era5_requests,
    required_firms_days,
)
from ai_earth_intelligence_and_forecasting_engine.data.observation import Observation
from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    build_dataset,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.historical_dataset import (
    ObservationIndex,
    iter_historical_rows,
)
from ai_earth_intelligence_and_forecasting_engine.forecast.spec import split_for_date

# 2x2 cells, so neighbor counts are exercised too.
TEST_BBOX = (-120.0, 37.0, -119.8, 37.2)
CELLS = build_california_grid(bbox=TEST_BBOX, resolution_deg=0.1)
CUTOFFS = [
    datetime(2020, 8, 1, 10, tzinfo=timezone.utc),
    datetime(2020, 8, 8, 10, tzinfo=timezone.utc),
    datetime(2020, 8, 15, 10, tzinfo=timezone.utc),
]


def _obs(observation_id: str, when: datetime, lat: float, lon: float, conf="n"):
    return Observation(
        observation_id=observation_id,
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=when,
        latitude=lat,
        longitude=lon,
        source_record_id=observation_id,
        ingested_at=when,
        confidence=conf,
    )


def _era5(valid_time: datetime, lat: float, lon: float, temperature: float):
    return ERA5Record(
        latitude=lat,
        longitude=lon,
        valid_time=valid_time,
        temperature_2m=temperature,
        total_precipitation=0.0,
        u_wind_10m=1.0,
        v_wind_10m=-1.0,
        dewpoint_2m=temperature - 10,
    )


# Fires spread over ~7 weeks: inside and outside every lookback and label
# window, exactly on window boundaries, and low-confidence (excluded).
OBSERVATIONS = [
    _obs(
        f"f{i}",
        CUTOFFS[0] - timedelta(days=40) + timedelta(hours=7 * i),
        lat,
        lon,
        conf,
    )
    for i, (lat, lon, conf) in enumerate(
        [(37.05, -119.95, "n"), (37.15, -119.85, "h"), (37.05, -119.85, "l")] * 60
    )
] + [
    _obs("on-cutoff", CUTOFFS[1], 37.05, -119.95),
    _obs("window-end", CUTOFFS[1] + timedelta(hours=24), 37.15, -119.95),
    _obs("lookback-edge", CUTOFFS[2] - timedelta(days=30), 37.15, -119.85),
]
ERA5 = [
    _era5(cutoff + timedelta(hours=offset), lat, lon, 290.0 + offset)
    for cutoff in CUTOFFS
    for offset in (-48, -1, 0, 1)
    for lat, lon in [(37.05, -119.95), (37.15, -119.85)]
]
GEOGRAPHY = [
    GeographyCell(
        latitude=37.05,
        longitude=-119.95,
        elevation_m=800.0,
        slope_deg=5.0,
        land_cover_class=10,
    ),
]


def _era5_for_cutoff(cutoff: datetime) -> list[ERA5Record]:
    start, _ = observation_window(cutoff)
    return [record for record in ERA5 if start < record.valid_time <= cutoff]


def test_per_cutoff_build_is_identical_to_one_full_build_dataset_call():
    full = build_dataset(OBSERVATIONS, ERA5, GEOGRAPHY, CELLS, CUTOFFS, bbox=TEST_BBOX)

    chunked = [
        row
        for rows in iter_historical_rows(
            ObservationIndex(OBSERVATIONS),
            _era5_for_cutoff,
            GEOGRAPHY,
            CELLS,
            CUTOFFS,
            bbox=TEST_BBOX,
        )
        for row in rows
    ]

    assert chunked == full
    # The fixture must actually exercise both classes and the features,
    # or equality would be trivially true.
    assert {row.target for row in full} == {0, 1}
    assert any(row.previous_30d_count > 0 for row in full)
    assert any(row.neighboring_previous_24h_count > 0 for row in full)


def test_observation_index_window_is_open_start_closed_end():
    index = ObservationIndex(OBSERVATIONS)
    start, end = CUTOFFS[1] - timedelta(hours=1), CUTOFFS[1]

    ids = {obs.observation_id for obs in index.between(start, end)}

    assert "on-cutoff" in ids
    assert all(start < obs.observed_at <= end for obs in index.between(start, end))


def test_historical_cutoffs_follow_the_pre_registered_rule():
    cutoffs = historical_cutoffs()

    assert len(cutoffs) == 22 * 6
    assert all(
        cutoff.hour == 10 and cutoff.tzinfo is timezone.utc for cutoff in cutoffs
    )
    assert all(6 <= cutoff.month <= 10 for cutoff in cutoffs)
    assert cutoffs[0] == datetime(2019, 6, 1, 10, tzinfo=timezone.utc)
    assert all(
        (later - earlier).days in (7, 365 - 147, 366 - 147)
        for earlier, later in zip(cutoffs, cutoffs[1:])
    )
    splits = {split_for_date(cutoff.date()) for cutoff in cutoffs}
    assert splits == {"train", "validation", "test"}


def test_required_firms_days_cover_every_lookback_and_label_window():
    days = set(required_firms_days(CUTOFFS))

    for cutoff in CUTOFFS:
        start, end = observation_window(cutoff)
        assert start.date() in days and end.date() in days
        assert start == cutoff - timedelta(days=30)
        assert end == cutoff + timedelta(hours=24)


def test_firms_spans_are_contiguous_and_within_the_api_limit():
    days = [date(2020, 8, 1) + timedelta(days=i) for i in range(12)] + [
        date(2020, 9, 1)
    ]

    spans = firms_spans(days)

    assert spans == [
        FIRMSSpan(date(2020, 8, 1), 5),
        FIRMSSpan(date(2020, 8, 6), 5),
        FIRMSSpan(date(2020, 8, 11), 2),
        FIRMSSpan(date(2020, 9, 1), 1),
    ]
    assert all(1 <= span.day_range <= FIRMS_MAX_DAY_RANGE for span in spans)
    assert parse_span_file_name(spans[0].file_name) == spans[0]


def test_era5_requests_group_cutoff_days_by_month_at_the_cutoff_hour():
    requests = required_era5_requests(historical_cutoffs(2020, 2020))

    assert [(year, month) for year, month, _, _ in requests] == [
        (2020, month) for month in range(6, 11)
    ]
    assert requests[0][2] == [1, 8, 15, 22, 29]
    assert all(hour == "10:00" for *_, hour in requests)
