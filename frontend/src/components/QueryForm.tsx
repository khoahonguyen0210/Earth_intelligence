import { useState, type FormEvent } from "react";
import type { AnalysisRequest, Intent, Operation, RegionKind } from "../api/types";

interface QueryFormProps {
  onSubmit: (request: AnalysisRequest) => void;
  disabled: boolean;
}

const OPERATION_OPTIONS: { value: Operation; label: string; intent: Intent }[] = [
  { value: "count", label: "Count", intent: "count" },
  { value: "daily_aggregate", label: "Daily breakdown", intent: "aggregate" },
  { value: "weekly_aggregate", label: "Weekly breakdown", intent: "aggregate" },
  { value: "map", label: "Map", intent: "map" },
];

const NAMED_REGIONS = [
  "california",
  "northern_california",
  "southern_california",
  "central_valley",
  "bay_area",
];

export function QueryForm({ onSubmit, disabled }: QueryFormProps) {
  const [question, setQuestion] = useState(
    "How many fires occurred in California?",
  );
  const [operation, setOperation] = useState<Operation>("count");
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
  const [start, setStart] = useState("2024-08-01");
  const [end, setEnd] = useState("2024-08-20");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const operationOption = OPERATION_OPTIONS.find((o) => o.value === operation);
    if (!operationOption) {
      return;
    }

    const region: AnalysisRequest["region"] =
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

    onSubmit({
      question,
      intent: operationOption.intent,
      region,
      time_range: { start, end },
      operation,
    });
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Earth analysis query form">
      <label>
        Question
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          required
        />
      </label>

      <label>
        Operation
        <select
          value={operation}
          onChange={(event) => setOperation(event.target.value as Operation)}
        >
          {OPERATION_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

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

      <fieldset>
        <legend>Time range</legend>
        <label>
          Start
          <input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            required
          />
        </label>
        <label>
          End
          <input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            required
          />
        </label>
      </fieldset>

      <button type="submit" disabled={disabled}>
        {disabled ? "Running..." : "Run analysis"}
      </button>
    </form>
  );
}
