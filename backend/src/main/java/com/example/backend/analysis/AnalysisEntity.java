package com.example.backend.analysis;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * The JPA row shape for the analyses table (Task 6.3). request/result/
 * evidence are stored as raw JSON text in jsonb columns -- AnalysisStore
 * does the Analysis record <-> JSON conversion, so this class is a pure
 * persistence detail the rest of the analysis package never sees.
 */
@Entity
@Table(name = "analyses")
public class AnalysisEntity {

    @Id
    private String id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", nullable = false)
    private String request;

    @Column(nullable = false)
    private String status;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private String result;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private String evidence;

    private String error;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AnalysisEntity() {
        // JPA
    }

    public AnalysisEntity(
            String id, String request, String status, String result, String evidence, String error, Instant createdAt) {
        this.id = id;
        this.request = request;
        this.status = status;
        this.result = result;
        this.evidence = evidence;
        this.error = error;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getRequest() {
        return request;
    }

    public String getStatus() {
        return status;
    }

    public String getResult() {
        return result;
    }

    public String getEvidence() {
        return evidence;
    }

    public String getError() {
        return error;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
