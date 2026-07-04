# ERA5-Land Input Contract

## Provider

Copernicus Climate Data Store (CDS), ECMWF.

## Primary Environmental Product

ERA5-Land hourly data from 1950 to present.

Dataset identifier:

`reanalysis-era5-land`

## Access Method

CDS API (`cdsapi` Python client).

The pipeline accesses historical environmental data through the CDS API using a personal access token.

Request parameters:

- dataset (`reanalysis-era5-land`)
- variables
- year/month/day
- time (hour)
- geographic area
- output format

The geographic area uses:

`north,west,south,east`

The API request is limited to a bounded historical sample.

## Locked Variables

Exactly:

- `2m_temperature`
- `total_precipitation`
- `10m_u_component_of_wind`
- `10m_v_component_of_wind`
- `2m_dewpoint_temperature` (used to derive relative humidity)

Relative humidity is derived from 2 m temperature and 2 m dewpoint temperature; ERA5-Land does not publish relative humidity directly.

## Geographic Scope

California.

The initial pipeline sample uses the same fixed California bounding box as the FIRMS adapter.

The exact bounding box is stored in the adapter configuration and provenance metadata.

## Historical Retrieval

Historical data is requested using a fixed date and hour.

The initial deterministic sample will use:

- fixed geographic area
- fixed historical date
- fixed hour
- fixed variable list

## Format

Raw provider response:

NetCDF.

The raw response is saved before parsing or normalization.

## Time

Provider `valid_time` is normalized to UTC.

## Provider Metadata

The adapter preserves provider metadata where available, including:

- latitude
- longitude
- valid_time
- variable short names
- variable units

## Reproducibility

A retrieval is reproducible when the following are recorded:

- provider
- dataset
- geographic area
- historical date
- hour
- variable list
- request parameters
- retrieval timestamp
- raw response checksum

## Raw Data Contract

Raw ERA5-Land responses are stored under:

`data/raw/era5/`

Raw provider data is not committed to Git.

## Credentials

The adapter reads CDS credentials from environment variables:

- `CDSAPI_URL`
- `CDSAPI_KEY`

Credentials are never committed to Git.

## Primary Documentation

ERA5-Land hourly data dataset page:

https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land

CDS API how-to:

https://cds.climate.copernicus.eu/how-to-api
