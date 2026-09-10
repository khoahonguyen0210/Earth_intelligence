package com.example.backend.analysis;

import java.util.Optional;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;

/**
 * Durable Postgres-backed storage for analyses. save/find present a
 * stable shape so callers like AnalysisController don't need to know how
 * persistence is implemented underneath.
 */
@Repository
public class AnalysisStore {

    private final AnalysisJpaRepository repository;
    private final ObjectMapper objectMapper;

    public AnalysisStore(AnalysisJpaRepository repository, ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    public void save(Analysis analysis) {
        repository.save(toEntity(analysis));
    }

    public Optional<Analysis> find(String id) {
        return repository.findById(id).map(this::toDomain);
    }

    private AnalysisEntity toEntity(Analysis analysis) {
        return new AnalysisEntity(
                analysis.id(),
                objectMapper.writeValueAsString(analysis.request()),
                analysis.status().name(),
                analysis.result() == null ? null : objectMapper.writeValueAsString(analysis.result()),
                analysis.evidence() == null ? null : objectMapper.writeValueAsString(analysis.evidence()),
                analysis.error(),
                analysis.createdAt());
    }

    private Analysis toDomain(AnalysisEntity entity) {
        return new Analysis(
                entity.getId(),
                objectMapper.readValue(entity.getRequest(), AnalysisRequest.class),
                entity.getCreatedAt(),
                Analysis.Status.valueOf(entity.getStatus()),
                entity.getResult() == null ? null : objectMapper.readValue(entity.getResult(), Object.class),
                entity.getEvidence() == null ? null : objectMapper.readValue(entity.getEvidence(), Object.class),
                entity.getError());
    }
}
