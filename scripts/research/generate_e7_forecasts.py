import argparse
import json
import time
from pathlib import Path

import torch

from ai_earth_intelligence_and_forecasting_engine.data.history import (
    historical_cutoffs,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.forecast import (
    APPROXIMATE_INDEX_VERSION,
    INDEX_LEVELS_HPA,
    INDEX_VERSION,
    forecast_cutoff,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.store import (
    cutoff_file_name,
    save_cutoff_forecast,
)
from ai_earth_intelligence_and_forecasting_engine.earth2.timing import SPLIT_YEARS

OUTPUT_DIR = Path("ml/artifacts/e7_forecasts")


def e7_cutoffs():
    years = sorted(year for group in SPLIT_YEARS.values() for year in group)
    return [cutoff for year in years for cutoff in historical_cutoffs(year, year)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="SFNO")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    arguments = parser.parse_args()

    import earth2studio
    from earth2studio.data import ARCO
    from earth2studio.models import px

    model_class = getattr(px, arguments.model)
    model = model_class.load_model(model_class.load_default_package())
    model = model.to("cuda").eval()
    data = ARCO()

    output = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    metadata_path = output / "metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path.exists()
        else {"seconds": {}, "approximate": {}}
    )
    metadata.update(
        model=arguments.model,
        earth2studio=earth2studio.__version__,
        torch=torch.__version__,
        gpu=torch.cuda.get_device_name(0),
        data_source="ERA5 from ARCO (Google Cloud)",
        initialization="latest 6-hour analysis time at or before the cutoff",
        levels_hpa=list(INDEX_LEVELS_HPA),
    )

    cutoffs = e7_cutoffs()[: arguments.limit]
    for number, cutoff in enumerate(cutoffs, start=1):
        if (output / cutoff_file_name(cutoff)).exists():
            continue
        started = time.perf_counter()
        forecast = forecast_cutoff(model, data, cutoff)
        save_cutoff_forecast(forecast, output)
        seconds = round(time.perf_counter() - started, 1)
        metadata["seconds"][cutoff.isoformat()] = seconds
        metadata["approximate"][cutoff.isoformat()] = forecast.approximate
        metadata["index_version"] = (
            APPROXIMATE_INDEX_VERSION
            if any(metadata["approximate"].values())
            else INDEX_VERSION
        )
        metadata["peak_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[{number}/{len(cutoffs)}] {cutoff.isoformat()} {seconds} s")

    print(f"{len(list(output.glob('forecast_*.npz')))} forecasts in {output}")


if __name__ == "__main__":
    main()
