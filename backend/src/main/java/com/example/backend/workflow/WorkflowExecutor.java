package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;
import com.example.backend.workflow.WorkflowTaskDispatcher.DispatchOutcome;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Task 8.3: walks a Workflow's nodes to completion in dependency order,
 * dispatching each one through a WorkflowTaskDispatcher once Task 8.2's
 * state machine says it may run, and recording the real outcome.
 *
 * Synchronous and single-call, not queue-backed: unlike ForecastWorker
 * (Task 6.5), which polls a Redis queue across separate scheduled
 * invocations, `execute` runs a whole workflow to a fixed point (every
 * node reaches a terminal state) in one call, retrying in-line rather
 * than re-enqueueing. This is the right shape to prove the DAG-walking
 * algorithm itself against the handbook's own example DAG (get_data ->
 * validate -> build_features -> run_forecast, fanning out to
 * get_result_evidence/generate_map); wiring this into a real async,
 * restart-safe queue the way ForecastWorker already is for a single job
 * is later work, not this task's -- see docs/workflow-execution.md.
 *
 * A node whose dependency did not succeed is marked CANCELLED (not
 * FAILED): it was never itself attempted, so it never actually failed --
 * the real failure already lives on the dependency's own node.
 */
public class WorkflowExecutor {

    private final WorkflowTaskDispatcher dispatcher;
    private final Clock clock;
    private final int maxAttempts;

    public WorkflowExecutor(WorkflowTaskDispatcher dispatcher, Clock clock, int maxAttempts) {
        this.dispatcher = dispatcher;
        this.clock = clock;
        this.maxAttempts = maxAttempts;
    }

    /**
     * Runs `workflow` to completion. Throws IllegalArgumentException if
     * `workflow.validate()` (Task 8.1) reports any structural problem --
     * execution never starts on a workflow that isn't really a DAG.
     */
    public Workflow execute(Workflow workflow) {
        List<String> structuralErrors = workflow.validate();
        if (!structuralErrors.isEmpty()) {
            throw new IllegalArgumentException("cannot execute an invalid workflow: " + structuralErrors);
        }

        Map<String, WorkflowNode> nodesByTaskId = new LinkedHashMap<>();
        for (WorkflowNode node : workflow.nodes()) {
            nodesByTaskId.put(node.taskId(), node);
        }

        boolean progressed = true;
        while (progressed) {
            progressed = false;

            for (String taskId : List.copyOf(nodesByTaskId.keySet())) {
                WorkflowNode node = nodesByTaskId.get(taskId);
                WorkflowNode advanced = advance(node, nodesByTaskId);

                if (advanced != node) {
                    nodesByTaskId.put(taskId, advanced);
                    progressed = true;
                }
            }
        }

        return new Workflow(
                workflow.id(),
                workflow.name(),
                workflow.description(),
                workflow.createdAt(),
                List.copyOf(nodesByTaskId.values()));
    }

    private WorkflowNode advance(WorkflowNode node, Map<String, WorkflowNode> nodesByTaskId) {
        return switch (node.status()) {
            case PENDING -> advancePending(node, nodesByTaskId);
            // Both READY and RETRYING have a legal edge straight to RUNNING
            // (Task 8.2) -- runNode makes that one transition itself.
            case READY, RETRYING -> runNode(node);
            // A node already RUNNING when execute() is first called cannot
            // be this call's own doing -- within one execute() call, RUNNING
            // is always resolved to a terminal-ish status before returning
            // (see runNode). It can only be a leftover from a process that
            // crashed mid-dispatch (Task 8.4's own "restart and recover"
            // requirement) -- treat it as an interrupted attempt: retry it,
            // the same as any other transient failure would be.
            case RUNNING -> runNode(WorkflowStateMachine.transition(node, Status.RETRYING, clock.instant()));
            default -> node; // terminal states never change
        };
    }

    private WorkflowNode advancePending(WorkflowNode node, Map<String, WorkflowNode> nodesByTaskId) {
        List<WorkflowNode> dependencies = node.dependencies().stream().map(nodesByTaskId::get).toList();

        boolean anyDependencyUnreachable = dependencies.stream()
                .anyMatch(dependency -> dependency.status() == Status.FAILED
                        || dependency.status() == Status.CANCELLED);
        if (anyDependencyUnreachable) {
            return applyOutcome(node, Status.CANCELLED, null, "a dependency did not succeed");
        }

        boolean allDependenciesSucceeded =
                dependencies.stream().allMatch(dependency -> dependency.status() == Status.SUCCEEDED);
        if (allDependenciesSucceeded) {
            return WorkflowStateMachine.transition(node, Status.READY, clock.instant());
        }

        return node; // still waiting on at least one in-flight dependency
    }

    private WorkflowNode runNode(WorkflowNode readyOrRetrying) {
        WorkflowNode running = WorkflowStateMachine.transition(readyOrRetrying, Status.RUNNING, clock.instant());
        DispatchOutcome outcome = dispatcher.dispatch(running);
        WorkflowNode attempted = running.withAttempt(running.attempt() + 1, clock.instant());

        if (outcome.success()) {
            return applyOutcome(attempted, Status.SUCCEEDED, outcome.outputRef(), null);
        }

        if (outcome.transientFailure() && attempted.attempt() < maxAttempts) {
            return WorkflowStateMachine.transition(attempted, Status.RETRYING, clock.instant());
        }

        return applyOutcome(attempted, Status.FAILED, null, outcome.error());
    }

    /** Validates the transition (Task 8.2) before recording an outcome that carries more than just status. */
    private WorkflowNode applyOutcome(WorkflowNode node, Status status, String outputRef, String error) {
        Instant now = clock.instant();

        if (!WorkflowStateMachine.isLegalTransition(node.status(), status)) {
            throw new IllegalStateTransitionException(node.taskId(), node.status(), status);
        }

        return node.withOutcome(status, outputRef, error, now);
    }
}
