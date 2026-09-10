package com.example.backend.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/**
 * One node in a workflow DAG: task_id, task_type, dependencies, status,
 * attempt, input/output references, timestamps, error.
 *
 * Mirrors the Python planner's PlanStep
 * (ai_earth_intelligence_and_forecasting_engine.planner.validator.PlanStep
 * -- step_id/tool/input/depends_on) plus the runtime state a validated
 * Plan does not carry: a Plan is a static, unexecuted proposal: a
 * WorkflowNode is one of its steps once accepted for execution.
 *
 * inputRef/outputRef are opaque reference strings (a JSON blob, an
 * object-storage key, a `$step_id.field` reference per
 * planner.validator's own convention) rather than the raw value itself
 * -- this record does not interpret them, the same way PlanStep's own
 * `input` is left uninterpreted at the plan layer.
 *
 * Persisting this to the `jobs`/`workflows` tables is WorkflowStore's
 * job, not this one -- see docs/workflow-dag-schema.md.
 */
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
