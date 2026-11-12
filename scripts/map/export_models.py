import json
import shutil
from pathlib import Path

from ai_earth_intelligence_and_forecasting_engine.earth2.e7 import E7_VERSION
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import LEAD_DAYS

E7_DIR = Path("ml/artifacts/e7_multi_day_v1")
OUTPUT_DIR = Path("map/models")


def main() -> None:
    metrics = json.loads((E7_DIR / "metrics.json").read_text(encoding="utf-8"))
    config = json.loads((E7_DIR / "config.json").read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for lead in LEAD_DAYS:
        shutil.copyfile(
            E7_DIR / "models" / f"lead_{lead}.json", OUTPUT_DIR / f"lead_{lead}.json"
        )
    metadata = {
        "version": E7_VERSION,
        "trained_on": config["split_years"],
        "weather_model": config["forecast_model"],
        "index_version": config["index_version"],
        "test_pr_auc": {
            str(report["lead_day"]): report["pr_auc"]["with_forecast_weather"]
            for report in metrics["leads"]
        },
    }
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
