const BINS = [
  { upTo: 0.01, color: "#ffffcc", label: "under 1%" },
  { upTo: 0.02, color: "#fed976", label: "1 to 2%" },
  { upTo: 0.05, color: "#feb24c", label: "2 to 5%" },
  { upTo: 0.1, color: "#fd8d3c", label: "5 to 10%" },
  { upTo: 0.2, color: "#e31a1c", label: "10 to 20%" },
  { upTo: Infinity, color: "#800026", label: "20% or more" },
];
const SOUTH = 32.5;
const WEST = -124.5;
const STEP = 0.1;

const colorFor = (value) => BINS.find((bin) => value < bin.upTo).color;
const formatTime = (iso) =>
  new Date(iso).toLocaleString("en-US", {
    timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }) + " UTC";
const formatDay = (iso) =>
  new Date(iso).toLocaleDateString("en-US", { timeZone: "UTC", month: "short", day: "numeric" });

function cellBounds(tile) {
  const [, row, column] = tile.split("_").map(Number);
  const south = SOUTH + row * STEP;
  const west = WEST + column * STEP;
  return [[south, west], [south + STEP, west + STEP]];
}

function drawLegend() {
  document.getElementById("legend").innerHTML = BINS.map(
    (bin) => `<span><i style="background:${bin.color}"></i>${bin.label}</span>`
  ).join("");
}

function drawRuns(runs) {
  const body = document.getElementById("runs");
  body.innerHTML = "";
  runs.slice().reverse().slice(0, 10).forEach((run) => {
    const row = document.createElement("tr");
    [
      run.cutoff ? formatTime(run.cutoff) : "-",
      run.status || "-",
      run.minutes != null ? `${run.minutes} min` : "-",
      run.gpu_seconds != null ? `${Math.round(run.gpu_seconds / 60)} min` : "-",
    ].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
}

async function start() {
  drawLegend();
  const map = L.map("map", { preferCanvas: true }).setView([37.2, -119.4], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 12,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  const status = document.getElementById("status");
  let risk;
  try {
    const response = await fetch("risk.json", { cache: "no-store" });
    if (!response.ok) throw new Error(response.statusText);
    risk = await response.json();
  } catch (error) {
    status.textContent = "The latest forecast could not be loaded.";
    return;
  }

  document.getElementById("cutoff").textContent = formatTime(risk.cutoff);
  document.getElementById("start").textContent = formatTime(risk.forecast_start);
  document.getElementById("weather").textContent = risk.model.weather_model || "-";
  document.getElementById("model").textContent = risk.model.version || "-";

  const shapes = risk.tiles.map((tile) =>
    L.rectangle(cellBounds(tile), { stroke: false, fillOpacity: 0.7 }).addTo(map)
  );

  const buttons = document.getElementById("days");
  function show(index) {
    const lead = risk.leads[index];
    shapes.forEach((shape, position) => {
      const value = lead.risk[position];
      shape.setStyle({ fillColor: colorFor(value) });
      shape.bindTooltip(`${(value * 100).toFixed(1)}% on ${formatDay(lead.to)}`);
    });
    [...buttons.children].forEach((button, position) =>
      button.setAttribute("aria-pressed", String(position === index))
    );
  }
  risk.leads.forEach((lead, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Day +${lead.lead_day} (to ${formatDay(lead.to)})`;
    button.addEventListener("click", () => show(index));
    buttons.appendChild(button);
  });
  show(0);

  try {
    const response = await fetch("runs.json", { cache: "no-store" });
    if (response.ok) drawRuns(await response.json());
  } catch (error) {
    drawRuns([]);
  }
}

start();
