"""Build elevation/slope/land-cover features for every California grid cell.

Reads Copernicus GLO-30 (30 m) and ESA WorldCover v200 (1/8 overview)
COGs tile by tile from their public AWS buckets and writes one CSV row
per 0.1-degree cell, plus provenance.

    python scripts/data/build_statewide_geography.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Avoid a directory listing per remote COG open (GDAL's /vsicurl default).
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")

from ai_earth_intelligence_and_forecasting_engine.data.geography import (  # noqa: E402
    DEM_SOURCE,
    LANDCOVER_SOURCE,
    save_geography_records,
)
from ai_earth_intelligence_and_forecasting_engine.data.grid import (  # noqa: E402
    CALIFORNIA_BBOX,
    GRID_RESOLUTION_DEG,
)
from ai_earth_intelligence_and_forecasting_engine.data.provenance import (  # noqa: E402
    compute_file_checksum,
)
from ai_earth_intelligence_and_forecasting_engine.data.statewide_geography import (  # noqa: E402
    LANDCOVER_OVERVIEW_FACTOR,
    build_statewide_geography,
    one_degree_tiles,
)

OUTPUT_PATH = Path("data/raw/geography/california_geography.csv")


def main() -> None:
    started = datetime.now(timezone.utc)
    cells = build_statewide_geography(
        CALIFORNIA_BBOX,
        GRID_RESOLUTION_DEG,
        workers=4,
        progress=lambda n, total, count: print(f"[{n}/{total}] tile: {count} cells", flush=True),
    )
    save_geography_records(cells, OUTPUT_PATH)

    provenance = {
        "dem_source": DEM_SOURCE,
        "dem_resolution": "30 m (native)",
        "landcover_source": LANDCOVER_SOURCE,
        "landcover_resolution": f"1/{LANDCOVER_OVERVIEW_FACTOR} COG overview (~80 m)",
        "bbox": list(CALIFORNIA_BBOX),
        "resolution_deg": GRID_RESOLUTION_DEG,
        "tiles": len(one_degree_tiles(CALIFORNIA_BBOX)),
        "cells": len(cells),
        "retrieved_at": started.isoformat(),
        "checksum": compute_file_checksum(OUTPUT_PATH),
        "checksum_algorithm": "sha256",
    }
    OUTPUT_PATH.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    print(f"{len(cells)} cells -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
