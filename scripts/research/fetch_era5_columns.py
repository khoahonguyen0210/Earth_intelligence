import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from ai_earth_intelligence_and_forecasting_engine.kernels.fixtures import (
    FCN3_LEVELS,
    era5_variables,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", default="2025-08-03T06:00:00")
    parser.add_argument("--output", type=Path, default=Path("era5_columns.pt"))
    arguments = parser.parse_args()

    from earth2studio.data import ARCO, fetch_data
    from earth2studio.utils.time import to_time_array

    variables = era5_variables()
    x, coords = fetch_data(
        ARCO(),
        to_time_array([datetime.fromisoformat(arguments.time)]),
        np.array(variables),
        np.array([np.timedelta64(0, "h")]),
        device=torch.device("cpu"),
    )
    names = [str(name) for name in coords["variable"]]
    fields = {
        name: x[0, 0, names.index(name)].float().contiguous() for name in variables
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "time": arguments.time,
            "levels": list(FCN3_LEVELS),
            "fields": fields,
            "latitude": np.asarray(coords["lat"]),
            "longitude": np.asarray(coords["lon"]),
        },
        arguments.output,
    )
    print(f"saved {len(fields)} fields of shape {tuple(fields['t2m'].shape)}")


if __name__ == "__main__":
    main()
