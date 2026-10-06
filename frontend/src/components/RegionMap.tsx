const REFERENCE_BBOX: [number, number, number, number] = [
  -124.5, 32.5, -114.0, 42.0,
];

const VIEW_SIZE = 260;
const PADDING_LEFT = 34;
const PADDING_RIGHT = 12;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 26;
const GRID_STEP_DEG = 2;

interface RegionMapProps {
  bbox: [number, number, number, number];
  label?: string | null;
}

function range(start: number, stop: number, step: number): number[] {
  const values: number[] = [];
  let value = Math.ceil(start / step) * step;
  while (value <= stop) {
    values.push(value);
    value += step;
  }
  return values;
}

export function RegionMap({ bbox, label }: RegionMapProps) {
  const [west, south, east, north] = bbox;
  const [refWest, refSouth, refEast, refNorth] = REFERENCE_BBOX;

  const frameWest = Math.min(refWest, west);
  const frameSouth = Math.min(refSouth, south);
  const frameEast = Math.max(refEast, east);
  const frameNorth = Math.max(refNorth, north);

  const plotWidth = VIEW_SIZE - PADDING_LEFT - PADDING_RIGHT;
  const plotHeight = VIEW_SIZE - PADDING_TOP - PADDING_BOTTOM;
  const scaleX = plotWidth / (frameEast - frameWest);
  const scaleY = plotHeight / (frameNorth - frameSouth);

  function project(lon: number, lat: number): [number, number] {
    const x = PADDING_LEFT + (lon - frameWest) * scaleX;
    const y = PADDING_TOP + (frameNorth - lat) * scaleY;
    return [x, y];
  }

  const [refX0, refY0] = project(refWest, refNorth);
  const [refX1, refY1] = project(refEast, refSouth);
  const [x0, y0] = project(west, north);
  const [x1, y1] = project(east, south);

  const lonGridlines = range(refWest, refEast, GRID_STEP_DEG);
  const latGridlines = range(refSouth, refNorth, GRID_STEP_DEG);

  return (
    <svg
      role="img"
      aria-label={`Map of queried region${label ? `: ${label}` : ""}`}
      width={VIEW_SIZE}
      height={VIEW_SIZE}
      viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`}
    >
      <rect
        x={Math.min(refX0, refX1)}
        y={Math.min(refY0, refY1)}
        width={Math.abs(refX1 - refX0)}
        height={Math.abs(refY1 - refY0)}
        fill="#eef2f7"
        stroke="#94a3b8"
      />

      {lonGridlines.map((lon) => {
        const [gx0, gy0] = project(lon, refNorth);
        const [, gy1] = project(lon, refSouth);
        return (
          <line
            key={`lon-${lon}`}
            x1={gx0}
            y1={gy0}
            x2={gx0}
            y2={gy1}
            stroke="#cbd5e1"
            strokeWidth={1}
          />
        );
      })}
      {latGridlines.map((lat) => {
        const [gx0, gy0] = project(refWest, lat);
        const [gx1] = project(refEast, lat);
        return (
          <line
            key={`lat-${lat}`}
            x1={gx0}
            y1={gy0}
            x2={gx1}
            y2={gy0}
            stroke="#cbd5e1"
            strokeWidth={1}
          />
        );
      })}

      <rect
        data-testid="region-map-region"
        x={Math.min(x0, x1)}
        y={Math.min(y0, y1)}
        width={Math.max(Math.abs(x1 - x0), 2)}
        height={Math.max(Math.abs(y1 - y0), 2)}
        fill="#2563eb55"
        stroke="#2563eb"
        strokeWidth={2}
      />

      <rect
        x={Math.min(refX0, refX1)}
        y={Math.min(refY0, refY1)}
        width={Math.abs(refX1 - refX0)}
        height={Math.abs(refY1 - refY0)}
        fill="none"
        stroke="#475569"
        strokeWidth={1.5}
      />

      {lonGridlines.map((lon) => {
        const [gx] = project(lon, refSouth);
        return (
          <text
            key={`lon-label-${lon}`}
            x={gx}
            y={VIEW_SIZE - PADDING_BOTTOM + 14}
            fontSize="9"
            fill="#64748b"
            textAnchor="middle"
          >
            {lon}
          </text>
        );
      })}
      {latGridlines.map((lat) => {
        const [, gy] = project(refWest, lat);
        return (
          <text
            key={`lat-label-${lat}`}
            x={PADDING_LEFT - 6}
            y={gy + 3}
            fontSize="9"
            fill="#64748b"
            textAnchor="end"
          >
            {lat}
          </text>
        );
      })}

      <text
        x={PADDING_LEFT}
        y={PADDING_TOP + 12}
        fontSize="11"
        fontWeight="bold"
        fill="#1e293b"
      >
        {label ?? "queried region"}
      </text>
    </svg>
  );
}
