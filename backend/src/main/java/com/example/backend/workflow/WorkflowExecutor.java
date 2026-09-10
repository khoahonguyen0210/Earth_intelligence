package com.example.backend.workflow;

import com.example.backend.tracing.Spans;
import com.example.backend.workflow.WorkflowNode.Status;
import com.example.backend.workflow.WorkflowTaskDispatcher.DispatchOutcome;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.slf4j.event.Level;

/**
 * Walks a Workflow's nodes to completion in dependency order,
 * dispatching each one through a WorkflowTaskDispatcher once the state
 * machine says it may run, and recording the real outcome.
 *
 * Synchronous and single-call, not queue-backed: unlike ForecastWorker,
 * which polls a Redis queue across separate scheduled invocations,
 * `execute` runs a whole workflow to a fixed point (every node reaches
 * a terminal state) in one call, retrying in-line rather than
 * re-enqueueing. This is the right shape to prove the DAG-walking
 * algorithm itself (get_data -> validate -> build_features ->
 * run_forecast, fanning out to get_result_evidence/generate_map);
 * wiring this into a real async, restart-safe queue the way
 * ForecastWorker already is for a single job remains future work -- see
 * docs/workflow-execution.md.
 *
 * A node whose dependency did not succeed is marked CANCELLED (not
 * FAILED): it was never itself attempted, so it never actually failed --
 * the real failure already lives on the dependency's own node.
 *
 * Every log line written during execute() carries `workflow_id` (MDC);
 * each node attempt that ends logs one workflow_node_succeeded /
 * workflow_node_retry_scheduled / workflow_node_failed event, and the
 * run ends with workflow_finished.
 *
 * execute() is a `workflow.execute` span (a new trace unless one is
 * already running, e.g. an HTTP request that runs a workflow), and each
 * node attempt is a `workflow.node` child of it, tagged with the task
 * and its outcome -- so a trace shows the DAG's real execution order,
 * retries included (docs/tracing.md).
 */
public class WorkflowExecutor {

    public static final String MDC_WORKFLOW_ID = "workflow_id";

    private static final Logger log = LoggerFactory.getLogger(WorkflowExecutor.class);

    private final WorkflowTaskDispatcher dispatcher;
    private final Clock clock;
    private final int maxAttempts;
    private final Spans spans;

    public WorkflowExecutor(WorkflowTaskDispatcher dispatcher, Clock clock, int maxAttempts, Spans spans) {
        this.dispatcher = dispatcher;
        this.clock = clock;
        this.maxAttempts = maxAttempts;
        this.spans = spans;
    }

    /** Untraced -- for callers that do not run inside Spring. */
    public WorkflowExecutor(WorkflowTaskDispatcher dispatcher, Clock clock, int maxAttempts) {
        this(dispatcher, clock, maxAttempts, Spans.noop());
    }

    /**
     * Runs `workflow` to completion. Throws IllegalArgumentException if
     * `workflow.validate()` reports any structural problem -- execution
     * never starts on a workflow that isn't really a DAG.
     */
    public Workflow execute(Workflow workflow) {
        List<String> structuralErrors = workflow.validate();
        if (!structuralErrors.isEmpty()) {
            throw new IllegalArgumentException("cannot execute an invalid workflow: " + structuralErrors);
        }

        MDC.put(MDC_WORKFLOW_ID, workflow.id());
        try {
            return spans.root("workflow.execute", () -> runAndLog(workflow));
        } finally {
            MDC.remove(MDC_WORKFLOW_ID);
        }
    }

    private Workflow runAndLog(Workflow workflow) {
        spans.tag("workflow.id", workflow.id());
        spans.tag("workflow.name", workflow.name());
        Workflow finished = run(workflow);
        long failed = count(finished, Status.FAILED);
        spans.tag("workflow.succeeded", count(finished, Status.SUCCEEDED));
        spans.tag("workflow.failed", failed);
        spans.tag("workflow.cancelled", count(finished, Status.CANCELLED));
        if (failed > 0) {
            spans.fail(failed + " workflow node(s) failed");
        }
        log.atInfo()
                .addKeyValue("event", "workflow_finished")
                .addKeyValue("node_count", finished.nodes().size())
                .addKeyValue("succeeded", count(finished, Status.SUCCEEDED))
                .addKeyValue("failed", failed)
                .addKeyValue("cancelled", count(finished, Status.CANCELLED))
                .log("workflow finished");
        return finished;
    }

    private static long count(Workflow workflow, Status status) {
        return workflow.nodes().stream().filter(node -> node.status() == status).count();
    }

    private Workflow run(Workflow workflow) {
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
            // Both READY and RETRYING have a legal edge straight to
            // RUNNING -- runNode makes that one transition itself.
            case READY, RETRYING -> runNode(node);
            // A node already RUNNING when execute() is first called cannot
            // be this call's own doing -- within one execute() call, RUNNING
            // is always resolved to a terminal-ish status before returning
            // (see runNode). It can only be a leftover from a process that
            // crashed mid-dispatch -- treat it as an interrupted attempt:
            // retry it, the same as any other transient failure would be.
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
        return spans.child("workflow.node", () -> {
            spans.tag("workflow.task_id", readyOrRetrying.taskId());
            spans.tag("workflow.task_type", readyOrRetrying.taskType());
            WorkflowNode attempted = attemptNode(readyOrRetrying);
            spans.tag("workflow.attempt", attempted.attempt());
            spans.tag("workflow.node_status", attempted.status());
            if (attempted.status() != Status.SUCCEEDED) {
                spans.fail(attempted.error());
            }
            return attempted;
        });
    }

    private WorkflowNode attemptNode(WorkflowNode readyOrRetrying) {
        WorkflowNode running = WorkflowStateMachine.transition(readyOrRetrying, Status.RUNNING, clock.instant());
        long startNanos = System.nanoTime();
        DispatchOutcome outcome = dispatcher.dispatch(running);
        long durationMs = (System.nanoTime() - startNanos) / 1_000_000;
        WorkflowNode attempted = running.withAttempt(running.attempt() + 1, clock.instant());

        if (outcome.success()) {
            logNode(attempted, Level.INFO, "workflow_node_succeeded", durationMs, null);
            return applyOutcome(attempted, Status.SUCCEEDED, outcome.outputRef(), null);
        }

        if (outcome.transientFailure() && attempted.attempt() < maxAttempts) {
            logNode(attempted, Level.WARN, "workflow_node_retry_scheduled", durationMs, outcome.error());
            return WorkflowStateMachine.transition(attempted, Status.RETRYING, clock.instant());
        }

        logNode(attempted, Level.ERROR, "workflow_node_failed", durationMs, outcome.error());
        return applyOutcome(attempted, Status.FAILED, null, outcome.error());
    }

    private void logNode(WorkflowNode node, Level level, String event, long durationMs, String error) {
        log.atLevel(level)
                .addKeyValue("event", event)
                .addKeyValue("task_id", node.taskId())
                .addKeyValue("task_type", node.taskType())
                .addKeyValue("attempt", node.attempt())
                .addKeyValue("duration_ms", durationMs)
                .log(error == null ? "workflow node succeeded" : "workflow node failed: {}", error);
    }

    /** Validates the transition before recording an outcome that carries more than just status. */
    private WorkflowNode applyOutcome(WorkflowNode node, Status status, String outputRef, String error) {
        Instant now = clock.instant();

        if (!WorkflowStateMachine.isLegalTransition(node.status(), status)) {
            throw new IllegalStateTransitionException(node.taskId(), node.status(), status);
        }

        return node.withOutcome(status, outputRef, error, now);
    }
}
