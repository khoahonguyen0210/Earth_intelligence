package com.example.backend.workflow;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "jobs")
public class JobEntity {

    @Id
    private String id;

    @Column(name = "task_id", nullable = false)
    private String taskId;

    @Column(name = "workflow_id", nullable = false)
    private String workflowId;

    @Column(name = "job_type", nullable = false)
    private String jobType;

    @Column(nullable = false)
    private String status;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb", nullable = false)
    private String dependencies;

    @Column(nullable = false)
    private int attempt;

    @Column(name = "input_ref")
    private String inputRef;

    @Column(name = "output_ref")
    private String outputRef;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    private String error;

    protected JobEntity() {
        // JPA
    }

    public JobEntity(
            String id,
            String taskId,
            String workflowId,
            String jobType,
            String status,
            String dependencies,
            int attempt,
            String inputRef,
            String outputRef,
            Instant createdAt,
            Instant updatedAt,
            String error) {
        this.id = id;
        this.taskId = taskId;
        this.workflowId = workflowId;
        this.jobType = jobType;
        this.status = status;
        this.dependencies = dependencies;
        this.attempt = attempt;
        this.inputRef = inputRef;
        this.outputRef = outputRef;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
        this.error = error;
    }

    public String getId() {
        return id;
    }

    public String getTaskId() {
        return taskId;
    }

    public String getWorkflowId() {
        return workflowId;
    }

    public String getJobType() {
        return jobType;
    }

    public String getStatus() {
        return status;
    }

    public String getDependencies() {
        return dependencies;
    }

    public int getAttempt() {
        return attempt;
    }

    public String getInputRef() {
        return inputRef;
    }

    public String getOutputRef() {
        return outputRef;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public String getError() {
        return error;
    }
}
