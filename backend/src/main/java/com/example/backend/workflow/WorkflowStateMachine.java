package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;
import java.time.Instant;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

/**
 * Task 8.2 (Execution Handbook Phase 8): the legal transitions between a
 * WorkflowNode's seven states (Task 8.1's state space).
 *
 * ```text
 * PENDING   -> READY, CANCELLED
 * READY     -> RUNNING, CANCELLED
 * RUNNING   -> SUCCEEDED, FAILED, RETRYING, CANCELLED
 * RETRYING  -> RUNNING, CANCELLED
 * SUCCEEDED -> (terminal)
 * FAILED    -> (terminal)
 * CANCELLED -> (terminal)
 * ```
 *
 * PENDING never goes straight to RUNNING: a node only becomes eligible
 * to run once its dependencies are satisfied (Task 8.1's own
 * task_id/dependencies shape is what that check runs against), and
 * READY is the state that records that. RETRYING re-enters at RUNNING
 * directly, not through READY again -- a retry re-dispatches the same
 * already-ready node, it does not re-check dependencies a second time --
 * which mirrors how `ForecastWorker` (Task 6.5/6.6) already treats
 * PENDING and RETRYING as equally eligible to become RUNNING for a
 * single standalone job (a `Forecast` has no dependencies of its own, so
 * it never needed a distinct READY state at all; a `WorkflowNode` does).
 * Cancellation is legal from every non-terminal state, matching the
 * handbook's Task 6.6 "worker timeout -> recover/retry" and Task 9.5
 * fault-injection expectations that in-flight work can be stopped, not
 * only queued work.
 */
public final class WorkflowStateMachine {

    private static final Map<Status, Set<Status>> LEGAL_TRANSITIONS = buildLegalTransitions();

    private WorkflowStateMachine() {
    }

    private static Map<Status, Set<Status>> buildLegalTransitions() {
        Map<Status, Set<Status>> transitions = new EnumMap<>(Status.class);
        transitions.put(Status.PENDING, EnumSet.of(Status.READY, Status.CANCELLED));
        transitions.put(Status.READY, EnumSet.of(Status.RUNNING, Status.CANCELLED));
        transitions.put(
                Status.RUNNING,
                EnumSet.of(Status.SUCCEEDED, Status.FAILED, Status.RETRYING, Status.CANCELLED));
        transitions.put(Status.RETRYING, EnumSet.of(Status.RUNNING, Status.CANCELLED));
        transitions.put(Status.SUCCEEDED, EnumSet.noneOf(Status.class));
        transitions.put(Status.FAILED, EnumSet.noneOf(Status.class));
        transitions.put(Status.CANCELLED, EnumSet.noneOf(Status.class));
        return transitions;
    }

    public static boolean isLegalTransition(Status from, Status to) {
        return LEGAL_TRANSITIONS.get(from).contains(to);
    }

    public static Set<Status> legalNextStates(Status from) {
        return Set.copyOf(LEGAL_TRANSITIONS.get(from));
    }

    public static boolean isTerminal(Status status) {
        return LEGAL_TRANSITIONS.get(status).isEmpty();
    }

    /**
     * The one path Task 8.3's execution engine is meant to change a
     * node's status through: illegal transitions raise rather than
     * silently applying, the same "cannot bypass the validator"
     * property Task 7.2's plan validator already guarantees for a Plan.
     */
    public static WorkflowNode transition(WorkflowNode node, Status to, Instant updatedAt) {
        if (!isLegalTransition(node.status(), to)) {
            throw new IllegalStateTransitionException(node.taskId(), node.status(), to);
        }

        return node.withStatus(to, updatedAt);
    }
}
