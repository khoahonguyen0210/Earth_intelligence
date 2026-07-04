from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.data.observation import (
    Observation,
)


def test_observation_contains_canonical_fields():
    observed_at = datetime(2024, 8, 15, 10, 1, tzinfo=timezone.utc)
    ingested_at = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

    observation = Observation(
        observation_id="firms-2024-08-15-001",
        source="NASA_FIRMS",
        product="VIIRS_SNPP_SP",
        observed_at=observed_at,
        latitude=40.82067,
        longitude=-114.25546,
        source_record_id="firms-001",
        ingested_at=ingested_at,
        confidence="n",
    )

    assert observation.observation_id == "firms-2024-08-15-001"
    assert observation.source == "NASA_FIRMS"
    assert observation.product == "VIIRS_SNPP_SP"
    assert observation.observed_at == observed_at
    assert observation.latitude == 40.82067
    assert observation.longitude == -114.25546
    assert observation.source_record_id == "firms-001"
    assert observation.ingested_at == ingested_at
    assert observation.confidence == "n"