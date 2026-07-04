# California Grid Contract

## Purpose

Defines the fixed spatial grid that every downstream feature, label, and
forecast in this project is keyed to.

## Extent

The same California bounding box used by the FIRMS, ERA5-Land, and static
geography adapters:

```
west  = -124.5
south =  32.5
east  = -114.0
north =  42.0
```

This is a bounding-box definition of "California," not the true state
boundary polygon. It intentionally includes a border strip of neighboring
states/ocean; this matches how "California" is already scoped everywhere
else in the pipeline (FIRMS bbox, ERA5-Land bbox), so a single fixed
extent is used project-wide.

## Resolution

`0.1 x 0.1` degrees, matching the locked project grid.

## Grid Dimensions

```
width  = (east - west)  / resolution = 105
height = (north - south) / resolution =  95
cell_count = width * height = 9975
```

## Boundary Rule

Cell `(lat_index, lon_index)` covers the half-open interval:

```
longitude in [west + lon_index*resolution, west + (lon_index+1)*resolution)
latitude  in [south + lat_index*resolution, south + (lat_index+1)*resolution)
```

`lat_index` and `lon_index` both start at `0` at the bounding box's
south-west corner. The bounding box's east/north edges are the exclusive
upper bound of the grid — no cell extends past them, and no cell is
generated beyond the last full `0.1` degree step.

## Tile ID

Deterministic and derived only from grid indices, not floating-point
coordinates, so regenerating the grid always produces identical IDs:

```
tile_id = f"CA_{lat_index:04d}_{lon_index:04d}"
```

## Geometry

Each cell is stored as a GeoJSON `Polygon` (closed, counter-clockwise
exterior ring) covering `[min_lon, min_lat, max_lon, max_lat]`, plus a
`centroid_lon`/`centroid_lat` at the cell midpoint.

## Versioning

The grid carries a `grid_version` string (currently `v1`). Any future
change to the bounding box, resolution, tile ID scheme, or boundary rule
must increment this version rather than silently changing the existing
one, since downstream feature/label tables reference cells by `tile_id`.

## Output

Generation is deterministic and reproducible from code — the grid is not
committed to Git. Running `scripts/data/generate_grid.py` regenerates it
on demand.

```
data/processed/grid/california_grid_<version>.geojson
data/processed/grid/metadata.json
```

`metadata.json` records `grid_version`, `bbox`, `resolution_deg`,
`cell_count`, `boundary_rule`, and `created_at` for reproducibility.
