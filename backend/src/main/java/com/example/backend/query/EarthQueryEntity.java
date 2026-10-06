package com.example.backend.query;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "earth_queries")
public class EarthQueryEntity {

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

    protected EarthQueryEntity() {
    }

    public EarthQueryEntity(String id, String request, String status, String result, String error, Instant createdAt) {
        this.id = id;
        this.request = request;
        this.status = status;
        this.result = result;
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

    public String getError() {
        return error;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
