import { useState, type FormEvent } from "react";
import type { ForecastRequest, RegionKind } from "../api/types";

interface ForecastRequestFormProps {
  onSubmit: (request: ForecastRequest) => void;
  disabled: boolean;
}

const NAMED_REGIONS = [
  "california",
  "northern_california",
  "southern_california",
  "central_valley",
  "bay_area",
];

export function ForecastRequestForm({ onSubmit, disabled }: ForecastRequestFormProps) {
  const [regionKind, setRegionKind] = useState<RegionKind>("named");
  const [namedRegion, setNamedRegion] = useState("california");
  const [bbox, setBbox] = useState({
    west: -124.5,
    south: 32.5,
    east: -114.0,
    north: 42.0,
  });
  const [coordinates, setCoordinates] = useState({
    latitude: 37.5,
    longitude: -119.5,
  });
  const [cutoff, setCutoff] = useState("2024-08-21T00:00");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const region: ForecastRequest["region"] =
      regionKind === "named"
        ? { kind: "named", value: namedRegion }
        : regionKind === "bbox"
          ? {
              kind: "bbox",
              value: [bbox.west, bbox.south, bbox.east, bbox.north],
            }
          : {
              kind: "coordinates",
              value: [coordinates.latitude, coordinates.longitude],
            };

    onSubmit({ region, cutoff: `${cutoff}:00Z` });
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Forecast request form">
      <fieldset>
        <legend>Region</legend>
        <label>
          Kind
          <select
            value={regionKind}
            onChange={(event) => setRegionKind(event.target.value as RegionKind)}
          >
            <option value="named">Named region</option>
            <option value="bbox">Bounding box</option>
            <option value="coordinates">Coordinates</option>
          </select>
        </label>

        {regionKind === "named" && (
          <label>
            Region name
            <select
              value={namedRegion}
              onChange={(event) => setNamedRegion(event.target.value)}
            >
              {NAMED_REGIONS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}

        {regionKind === "bbox" && (
          <div>
            <label>
              West
              <input
                type="number"
                step="0.1"
                value={bbox.west}
                onChange={(event) =>
                  setBbox({ ...bbox, west: Number(event.target.value) })
                }
              />
            </label>
            <label>
              South
              <input
                type="number"
                step="0.1"
                value={bbox.south}
                onChange={(event) =>
                  setBbox({ ...bbox, south: Number(event.target.value) })
                }
              />
            </label>
            <label>
              East
              <input
                type="number"
                step="0.1"
                value={bbox.east}
                onChange={(event) =>
                  setBbox({ ...bbox, east: Number(event.target.value) })
                }
              />
            </label>
            <label>
              North
              <input
                type="number"
                step="0.1"
                value={bbox.north}
                onChange={(event) =>
                  setBbox({ ...bbox, north: Number(event.target.value) })
                }
              />
            </label>
          </div>
        )}

        {regionKind === "coordinates" && (
          <div>
            <label>
              Latitude
              <input
                type="number"
                step="0.01"
                value={coordinates.latitude}
                onChange={(event) =>
                  setCoordinates({
                    ...coordinates,
                    latitude: Number(event.target.value),
                  })
                }
              />
            </label>
            <label>
              Longitude
              <input
                type="number"
                step="0.01"
                value={coordinates.longitude}
                onChange={(event) =>
                  setCoordinates({
                    ...coordinates,
                    longitude: Number(event.target.value),
                  })
                }
              />
            </label>
          </div>
        )}
      </fieldset>

      <label>
        Cutoff (UTC)
        <input
          type="datetime-local"
          value={cutoff}
          onChange={(event) => setCutoff(event.target.value)}
          required
        />
      </label>

      <button type="submit" disabled={disabled}>
        {disabled ? "Forecast running..." : "Request forecast"}
      </button>
    </form>
  );
}
