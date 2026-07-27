package com.example.backend.forecast;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

/**
 * In-memory store. Phase 2/6 has no database yet (PostgreSQL/PostGIS
 * persistence is Task 6.3); this is intentionally not durable.
 */
@Repository
public class ForecastStore {

    private final Map<String, Forecast> forecasts = new ConcurrentHashMap<>();

    public void save(Forecast forecast) {
        forecasts.put(forecast.id(), forecast);
    }

    public Optional<Forecast> find(String id) {
        return Optional.ofNullable(forecasts.get(id));
    }
}
