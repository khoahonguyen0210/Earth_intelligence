package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

@Repository
public class ForecastStore {

    private final ForecastJpaRepository repository;
    private final ObjectMapper objectMapper;
    private final Spans spans;

    public ForecastStore(ForecastJpaRepository repository, ObjectMapper objectMapper, Spans spans) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.spans = spans;
    }

    public void save(Forecast forecast) {
        spans.child("forecast.store.save", () -> {
            spans.tag("db.system", "postgresql");
            spans.tag("forecast.status", forecast.status());
            repository.save(toEntity(forecast));
        });
    }

    public Optional<Forecast> find(String id) {
        return spans.child("forecast.store.find", () -> {
            spans.tag("db.system", "postgresql");
            return repository.findById(id).map(this::toDomain);
        });
    }

    public boolean claim(String id) {
        return spans.child("forecast.store.claim", () -> {
            spans.tag("db.system", "postgresql");
            return repository.claim(id, Instant.now()) == 1;
        });
    }

    public List<String> runningUnchangedSince(Instant before) {
        return repository.findRunningUnchangedSince(before);
    }

    public List<String> waitingUnchangedSince(Instant before) {
        return repository.findWaitingUnchangedSince(before);
    }

    public boolean endAbandonedAttempt(String id, Forecast.Status status, String error, Instant before) {
        return repository.endAbandonedAttempt(id, status.name(), error, before, Instant.now()) == 1;
    }

    public boolean touchWaiting(String id, Instant before) {
        return repository.touchWaiting(id, before, Instant.now()) == 1;
    }

    public Optional<Forecast> findByIdempotencyKey(String idempotencyKey) {
        return spans.child("forecast.store.find_by_idempotency_key", () -> {
            spans.tag("db.system", "postgresql");
            return repository.findByIdempotencyKey(idempotencyKey).map(this::toDomain);
        });
    }

    private ForecastEntity toEntity(Forecast forecast) {
        return new ForecastEntity(
                forecast.id(),
                objectMapper.writeValueAsString(forecast.request()),
                forecast.status().name(),
                forecast.result() == null ? null : objectMapper.writeValueAsString(forecast.result()),
                forecast.error(),
                forecast.createdAt(),
                forecast.attempts(),
                forecast.idempotencyKey(),
                forecast.traceParent(),
                Instant.now());
    }

    private Forecast toDomain(ForecastEntity entity) {
        return new Forecast(
                entity.getId(),
                objectMapper.readValue(entity.getRequest(), ForecastRequest.class),
                entity.getCreatedAt(),
                Forecast.Status.valueOf(entity.getStatus()),
                entity.getResult() == null ? null : objectMapper.readValue(entity.getResult(), Object.class),
                entity.getError(),
                entity.getAttempts(),
                entity.getIdempotencyKey(),
                entity.getTraceParent());
    }
}
