# NASA FIRMS Input Contract

## Provider

NASA Fire Information for Resource Management System (FIRMS).

## Primary Fire Product

VIIRS 375 m / Suomi-NPP.

Product identifier:

`VIIRS_SNPP_SP`

Processing type:

Standard Processing.

## Access Method

NASA FIRMS Area API.

The pipeline accesses historical active-fire data through the FIRMS Area API using a FIRMS MAP_KEY.

Request parameters:

- MAP_KEY
- source/product
- geographic bounding box
- day range
- historical date

The geographic bounding box uses:

`west,south,east,north`

The API request is limited to a bounded historical sample.

## Geographic Scope

California.

The initial pipeline sample uses a fixed California bounding box.

The exact bounding box is stored in the adapter configuration and provenance metadata.

## Historical Retrieval

Historical data is requested using a fixed date.

The initial deterministic sample will use:

- fixed geographic bounding box
- fixed historical date
- fixed product
- fixed day range

## Format

Raw provider response:

CSV.

The raw response is saved before parsing or normalization.

## Time

Provider acquisition date and acquisition time are normalized to UTC.

## Provider Metadata

The adapter preserves provider metadata where available, including:

- latitude
- longitude
- acquisition date
- acquisition time
- satellite
- instrument
- confidence
- version
- FRP
- scan
- track
- brightness temperature fields
- day/night indicator

## Reproducibility

A retrieval is reproducible when the following are recorded:

- provider
- product
- geographic bounding box
- historical date
- day range
- request parameters
- retrieval timestamp
- raw response checksum

## Raw Data Contract

Raw FIRMS responses are stored under:

`data/raw/firms/`

Raw provider data is not committed to Git.

## Primary Documentation

NASA FIRMS Active Fire Data:

https://firms.modaps.eosdis.nasa.gov/content/active_fire/

NASA FIRMS Area API:

https://firms.modaps.eosdis.nasa.gov/usfs/api/area/

NASA FIRMS API documentation:

https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html