import argparse
from datetime import datetime, timezone

from ai_earth_intelligence_and_forecasting_engine.models.harness import (
    SUPPORTED_MODELS,
    run_experiment,
)

TRAIN_CUTOFF = datetime(2020, 8, 15, 10, 0, tzinfo=timezone.utc)
VALIDATION_CUTOFF = datetime(2023, 8, 15, 10, 0, tzinfo=timezone.utc)
TEST_CUTOFF = datetime(2024, 8, 15, 10, 0, tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one model evaluation experiment end-to-end."
    )
    parser.add_argument("--model", required=True, choices=SUPPORTED_MODELS)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()

    result = run_experiment(
        model_name=args.model,
        experiment_id=args.experiment_id,
        train_cutoff=TRAIN_CUTOFF,
        validation_cutoff=VALIDATION_CUTOFF,
        test_cutoff=TEST_CUTOFF,
    )

    if result.succeeded:
        print(f"Experiment '{result.experiment_id}' succeeded.")
        print(f"Metrics: {result.metrics}")
    else:
        print(f"Experiment '{result.experiment_id}' honestly failed: {result.error}")

    print(f"Artifacts saved to: {result.paths.root}")


if __name__ == "__main__":
    main()
