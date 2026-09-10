package com.example.backend.forecast;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.tracing.Spans;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.dao.DataIntegrityViolationException;
import tools.jackson.databind.ObjectMapper;

/**
 * An in-memory ForecastJpaRepository for unit tests, with the database
 * behaviour the code relies on: the unique idempotency-key index and the
 * conditional claim -- a job is claimed only from PENDING/RETRYING, so a
 * second claim of the same job fails.
 */
final class InMemoryForecasts {

    private InMemoryForecasts() {
    }

    static ForecastStore store() {
        return store(Spans.noop());
    }

    static ForecastStore store(Spans spans) {
        return new ForecastStore(repository(), new ObjectMapper(), spans);
    }

    static ForecastJpaRepository repository() {
        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        Map<String, ForecastEntity> rows = new ConcurrentHashMap<>();

        when(repository.save(any())).thenAnswer(invocation -> {
            ForecastEntity entity = invocation.getArgument(0);
            boolean keyTaken = entity.getIdempotencyKey() != null && rows.values().stream()
                    .anyMatch(row -> !row.getId().equals(entity.getId())
                            && entity.getIdempotencyKey().equals(row.getIdempotencyKey()));
            if (keyTaken) {
                throw new DataIntegrityViolationException("duplicate idempotency_key");
            }
            rows.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(rows.get(invocation.getArgument(0))));
        when(repository.findByIdempotencyKey(any())).thenAnswer(invocation -> rows.values().stream()
                .filter(row -> invocation.getArgument(0).equals(row.getIdempotencyKey()))
                .findFirst());
        when(repository.claim(anyString(), any())).thenAnswer(invocation -> {
            String id = invocation.getArgument(0);
            ForecastEntity row = rows.get(id);
            if (row == null || !(row.getStatus().equals("PENDING") || row.getStatus().equals("RETRYING"))) {
                return 0;
            }
            rows.put(id, withStatus(row, "RUNNING", invocation.getArgument(1)));
            return 1;
        });
        return repository;
    }

    private static ForecastEntity withStatus(ForecastEntity row, String status, Instant updatedAt) {
        return new ForecastEntity(row.getId(), row.getRequest(), status, row.getResult(), row.getError(),
                row.getCreatedAt(), row.getAttempts(), row.getIdempotencyKey(), row.getTraceParent(), updatedAt);
    }
}
