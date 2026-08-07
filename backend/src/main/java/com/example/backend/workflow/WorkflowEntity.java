package com.example.backend.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * The JPA row shape for the `workflows` table (Task 6.3, schema only
 * until this task). WorkflowStore does the Workflow record <-> entity
 * conversion; this class is a pure persistence detail the rest of the
 * workflow package never sees.
 */
@Entity
@Table(name = "workflows")
public class WorkflowEntity {

    @Id
    private String id;

    @Column(nullable = false)
    private String name;

    private String description;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected WorkflowEntity() {
        // JPA
    }

    public WorkflowEntity(String id, String name, String description, Instant createdAt) {
        this.id = id;
        this.name = name;
        this.description = description;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getDescription() {
        return description;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
