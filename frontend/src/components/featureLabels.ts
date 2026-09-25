const FEATURE_LABELS: Record<string, string> = {
  previous_24h_count: "Fires in the past 24 hours",
  previous_72h_count: "Fires in the past 3 days",
  previous_7d_count: "Fires in the past 7 days",
  previous_30d_count: "Fires in the past 30 days",
  neighboring_previous_24h_count: "Fires in neighboring cells, past 24 hours",
  temperature_2m: "Air temperature",
  total_precipitation: "Precipitation",
  u_wind_10m: "East-west wind",
  v_wind_10m: "North-south wind",
  relative_humidity: "Relative humidity",
  elevation_m: "Elevation",
  slope_deg: "Slope",
  land_cover: "Land cover",
};

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

export function effectLabel(contribution: number): string {
  return contribution >= 0 ? "raises risk" : "lowers risk";
}
