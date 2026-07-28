package com.example.backend.forecast;

import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 6.3: durable Postgres-backed storage, replacing the earlier
 * in-memory ConcurrentHashMap. save/find keep the exact same shape as
 * before, so ForecastController is unchanged -- only this class's
 * internals moved from a Map to a real jsonb-backed table.
 */
@Repository
public class ForecastStore {

    private final ForecastJpaRepository repository;
    private final ObjectMapper objectMapper;

    public ForecastStore(ForecastJpaRepository repository, ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    public void save(Forecast forecast) {
        repository.save(toEntity(forecast));
    }

    public Optional<Forecast> find(String id) {
        return repository.findById(id).map(this::toDomain);
    }

    private ForecastEntity toEntity(Forecast forecast) {
        return new ForecastEntity(
                forecast.id(),
                objectMapper.writeValueAsString(forecast.request()),
                forecast.status().name(),
                forecast.result() == null ? null : objectMapper.writeValueAsString(forecast.result()),
                forecast.error(),
                forecast.createdAt());
    }

    private Forecast toDomain(ForecastEntity entity) {
        return new Forecast(
                entity.getId(),
                objectMapper.readValue(entity.getRequest(), ForecastRequest.class),
                entity.getCreatedAt(),
                Forecast.Status.valueOf(entity.getStatus()),
                entity.getResult() == null ? null : objectMapper.readValue(entity.getResult(), Object.class),
                entity.getError());
    }
}
