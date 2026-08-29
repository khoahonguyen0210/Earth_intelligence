package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 6.3: durable Postgres-backed storage, replacing the earlier
 * in-memory ConcurrentHashMap. save/find keep the exact same shape as
 * before, so ForecastController is unchanged -- only this class's
 * internals moved from a Map to a real jsonb-backed table.
 *
 * Task 13.3: each call is a child span (the "storage" hop of a trace);
 * the save that records a job's outcome is where its result lands, and
 * carries that final status as a tag.
 */
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

    /** Task 6.6: backs the "same idempotency key -> one logical job" rule. */
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
                forecast.traceParent());
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
