import os
from pathlib import Path

import requests

from ai_earth_intelligence_and_forecasting_engine.api.benchmark import (
    api_benchmark_result_to_dict,
    run_api_benchmark,
    save_api_benchmark_result,
)

BACKEND_BASE_URL = os.environ.get("FORECAST_API_BASE_URL", "http://localhost:8080")
REQUEST_COUNT = 50

# A real region/cutoff the backend actually resolves, not a throwaway
# value, so this measures the real validate-and-enqueue path.
FORECAST_REQUEST = {
    "region": {"kind": "named", "value": "california"},
    "cutoff": "2024-08-15T10:00:00Z",
}


def main() -> None:
    def send_request() -> None:
        response = requests.post(
            f"{BACKEND_BASE_URL}/forecasts", json=FORECAST_REQUEST, timeout=30
        )
        if response.status_code != 201:
            raise RuntimeError(
                f"unexpected status {response.status_code}: {response.text}"
            )

    result = run_api_benchmark("POST /forecasts", send_request, REQUEST_COUNT)

    output_path = Path("data/processed/benchmark/forecast_api_benchmark.json")
    save_api_benchmark_result(result, output_path)

    for key, value in api_benchmark_result_to_dict(result).items():
        print(f"{key}: {value}")

    print(f"Saved benchmark result to: {output_path}")


if __name__ == "__main__":
    main()
