# Static Geography Input Contract

## Elevation / Slope Source

Copernicus DEM GLO-30 (Global 30m Digital Surface Model).

Provider: European Space Agency / Copernicus, distributed via a public AWS
Open Data bucket.

## Land-Cover Source

ESA WorldCover 10m v200 (2021).

Provider: European Space Agency, distributed via a public AWS Open Data
bucket.

No second competing land-cover product is used.

## Access Method

Both sources are Cloud-Optimized GeoTIFFs (COGs) on public, unauthenticated
AWS S3 buckets. The adapter reads them via GDAL's `/vsicurl/` virtual
filesystem through `rasterio`, using a windowed read so only the pixels
covering the requested bounding box are downloaded — not the full tile.

No API key or account is required for either source.

## Tile Layout

Copernicus DEM GLO-30 is tiled in 1x1 degree tiles, named by their
south-west corner, e.g.:

```
Copernicus_DSM_COG_10_N37_00_W120_00_DEM
```

ESA WorldCover is tiled in 3x3 degree tiles, named by their south-west
corner, e.g.:

```
ESA_WorldCover_10m_2021_v200_N36W120_Map
```

The adapter derives the correct tile name from the bounding box centroid.
A bounding box that spans a tile boundary is not supported by the initial
adapter; the initial deterministic sample uses a bounding box fully inside
one DEM tile and one WorldCover tile.

## Geographic Scope

California.

The initial pipeline sample uses a small bounding box in the Sierra Nevada
foothills (chosen for real elevation relief, useful for verifying slope
computation), fully contained within DEM tile `N37W120` and WorldCover
tile `N36W120`.

## Derived Variables

- `elevation_m` — mean elevation per output grid cell, meters.
- `slope_deg` — mean slope per output grid cell, degrees. Computed from
  the native-resolution DEM via a finite-difference gradient (pixel
  spacing converted from degrees to meters using a latitude-corrected
  approximation), before resampling to the output grid.
- `land_cover_class` — WorldCover class code per output grid cell, chosen
  by majority (mode) resampling.

## Alignment

Both rasters are resampled onto a shared 0.1 x 0.1 degree lat/lon grid
covering the requested bounding box:

- elevation and slope use average resampling.
- land cover uses mode (majority) resampling.

This 0.1 degree resolution matches the locked project grid. Assignment
to the canonical grid's stable tile IDs happens once the grid artifact
from Task 1.6 exists.

## Format

Raw provider response: GeoTIFF (per-source windowed subset).

Raw subsets are saved before resampling.

## Reproducibility

A retrieval is reproducible when the following are recorded:

- DEM source and tile URL
- land-cover source and tile URL
- bounding box
- output grid resolution
- retrieval timestamp

## Raw Data Contract

Raw windowed subsets are stored under:

`data/raw/geography/`

Raw provider data is not committed to Git.

Aligned grid output and provenance metadata are stored under:

`data/processed/geography/`

Processed data is not committed to Git.

## Primary Documentation

Copernicus DEM GLO-30 (AWS Open Data Registry):

https://registry.opendata.aws/copernicus-dem/

ESA WorldCover:

https://esa-worldcover.org/en
