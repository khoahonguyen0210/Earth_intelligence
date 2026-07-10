// California bbox, matching the fixed extent used throughout the pipeline
// (FIRMS/ERA5-Land/geography/grid). Used as a reference frame so a small
// region still shows its position in context, not just fill the viewport.
const REFERENCE_BBOX: [number, number, number, number] = [
  -124.5, 32.5, -114.0, 42.0,
];

const VIEW_SIZE = 240;
const PADDING = 16;

interface RegionMapProps {
  bbox: [number, number, number, number];
  label?: string | null;
}

export function RegionMap({ bbox, label }: RegionMapProps) {
  const [west, south, east, north] = bbox;
  const [refWest, refSouth, refEast, refNorth] = REFERENCE_BBOX;

  const frameWest = Math.min(refWest, west);
  const frameSouth = Math.min(refSouth, south);
  const frameEast = Math.max(refEast, east);
  const frameNorth = Math.max(refNorth, north);

  const scaleX = (VIEW_SIZE - 2 * PADDING) / (frameEast - frameWest);
  const scaleY = (VIEW_SIZE - 2 * PADDING) / (frameNorth - frameSouth);

  function project(lon: number, lat: number): [number, number] {
    const x = PADDING + (lon - frameWest) * scaleX;
    const y = PADDING + (frameNorth - lat) * scaleY; // SVG y grows downward
    return [x, y];
  }

  const [refX0, refY0] = project(refWest, refNorth);
  const [refX1, refY1] = project(refEast, refSouth);
  const [x0, y0] = project(west, north);
  const [x1, y1] = project(east, south);

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
      {/* Redraw the California outline on top, stroke-only, so it stays
          visible even when the queried region covers the whole extent
          (otherwise the blue fill above hides it completely). */}
      <rect
        x={Math.min(refX0, refX1)}
        y={Math.min(refY0, refY1)}
        width={Math.abs(refX1 - refX0)}
        height={Math.abs(refY1 - refY0)}
        fill="none"
        stroke="#475569"
        strokeDasharray="4 3"
      />
      <text x={PADDING} y={VIEW_SIZE - 4} fontSize="11" fill="#334155">
        {label ?? "queried region"}
      </text>
    </svg>
  );
}
