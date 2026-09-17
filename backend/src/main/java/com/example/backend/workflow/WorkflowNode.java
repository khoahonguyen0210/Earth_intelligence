package com.example.backend.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record WorkflowNode(
        String taskId,
        String taskType,
        List<String> dependencies,
        Status status,
        int attempt,
        String inputRef,
        String outputRef,
        Instant createdAt,
        Instant updatedAt,
        String error) {

    /**
     * WorkflowStateMachine defines the legal transitions between these;
     * this only fixes the state space itself.
     */
    public enum Status {
        PENDING,
        READY,
        RUNNING,
        SUCCEEDED,
        FAILED,
        RETRYING,
        CANCELLED
    }

    public WorkflowNode {
        Objects.requireNonNull(taskId, "taskId");
        Objects.requireNonNull(taskType, "taskType");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(createdAt, "createdAt");
        Objects.requireNonNull(updatedAt, "updatedAt");
        dependencies = List.copyOf(dependencies == null ? List.of() : dependencies);
    }

    /** A freshly-created node: PENDING, no attempts yet, no output/error. */
    public static WorkflowNode pending(
            String taskId, String taskType, List<String> dependencies, String inputRef, Instant createdAt) {
        return new WorkflowNode(
                taskId, taskType, dependencies, Status.PENDING, 0, inputRef, null, createdAt, createdAt, null);
    }

    public WorkflowNode withStatus(Status status, Instant updatedAt) {
        return new WorkflowNode(
                taskId, taskType, dependencies, status, attempt, inputRef, outputRef, createdAt, updatedAt, error);
    }

    public WorkflowNode withOutcome(Status status, String outputRef, String error, Instant updatedAt) {
        return new WorkflowNode(
                taskId, taskType, dependencies, status, attempt, inputRef, outputRef, createdAt, updatedAt, error);
    }

    public WorkflowNode withAttempt(int attempt, Instant updatedAt) {
        return new WorkflowNode(
                taskId, taskType, dependencies, status, attempt, inputRef, outputRef, createdAt, updatedAt, error);
    }
}
