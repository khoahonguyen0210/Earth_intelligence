package com.example.backend.analysis;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

/**
 * In-memory store. Phase 2 has no database yet (PostgreSQL/PostGIS
 * persistence is Task 6.3); this is intentionally not durable.
 */
@Repository
public class AnalysisStore {

    private final Map<String, Analysis> analyses = new ConcurrentHashMap<>();

    public void save(Analysis analysis) {
        analyses.put(analysis.id(), analysis);
    }

    public Optional<Analysis> find(String id) {
        return Optional.ofNullable(analyses.get(id));
    }
}
