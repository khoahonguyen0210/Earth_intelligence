package com.example.backend.query;

import com.example.backend.tracing.Spans;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

@Repository
public class EarthQueryStore {

    private final EarthQueryJpaRepository repository;
    private final ObjectMapper objectMapper;
    private final Spans spans;

    public EarthQueryStore(EarthQueryJpaRepository repository, ObjectMapper objectMapper, Spans spans) {
        this.repository = repository;
        this.objectMapper = objectMapper;
        this.spans = spans;
    }

    public void save(EarthQuery query) {
        spans.child("earth_query.store.save", () -> {
            spans.tag("db.system", "postgresql");
            spans.tag("earth_query.status", query.status());
            repository.save(toEntity(query));
        });
    }

    public Optional<EarthQuery> find(String id) {
        return spans.child("earth_query.store.find", () -> {
            spans.tag("db.system", "postgresql");
            return repository.findById(id).map(this::toDomain);
        });
    }

    private EarthQueryEntity toEntity(EarthQuery query) {
        return new EarthQueryEntity(
                query.id(),
                objectMapper.writeValueAsString(query.request()),
                query.status().name(),
                query.result() == null ? null : objectMapper.writeValueAsString(query.result()),
                query.error(),
                query.createdAt());
    }

    private EarthQuery toDomain(EarthQueryEntity entity) {
        return new EarthQuery(
                entity.getId(),
                objectMapper.readValue(entity.getRequest(), EarthQueryRequest.class),
                entity.getCreatedAt(),
                EarthQuery.Status.valueOf(entity.getStatus()),
                entity.getResult() == null ? null : objectMapper.readValue(entity.getResult(), Object.class),
                entity.getError());
    }
}
