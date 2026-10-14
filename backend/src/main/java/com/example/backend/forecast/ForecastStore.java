package com.example.backend.forecast;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

public interface ForecastStore {

    void save(Forecast forecast);

    Optional<Forecast> find(String id);

    boolean claim(String id);

    List<String> runningUnchangedSince(Instant before);

    List<String> waitingUnchangedSince(Instant before);

    boolean endAbandonedAttempt(String id, Forecast.Status status, String error, Instant before);

    boolean touchWaiting(String id, Instant before);

    Optional<Forecast> findByIdempotencyKey(String idempotencyKey);
}
