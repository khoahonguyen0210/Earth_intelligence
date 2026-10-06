package com.example.backend.forecast;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "forecasts")
public class ForecastEntity {

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

    private String error;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private int attempts;

    @Column(name = "idempotency_key")
    private String idempotencyKey;

    @Column(name = "trace_parent")
    private String traceParent;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected ForecastEntity() {
    }

    public ForecastEntity(
            String id,
            String request,
            String status,
            String result,
            String error,
            Instant createdAt,
            int attempts,
            String idempotencyKey,
            String traceParent,
            Instant updatedAt) {
        this.id = id;
        this.request = request;
        this.status = status;
        this.result = result;
        this.error = error;
        this.createdAt = createdAt;
        this.attempts = attempts;
        this.idempotencyKey = idempotencyKey;
        this.traceParent = traceParent;
        this.updatedAt = updatedAt;
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

    public String getError() {
        return error;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public int getAttempts() {
        return attempts;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public String getTraceParent() {
        return traceParent;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
