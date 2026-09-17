package com.example.backend.workflow;

import com.example.backend.workflow.WorkflowNode.Status;
import java.time.Instant;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

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

    public static WorkflowNode transition(WorkflowNode node, Status to, Instant updatedAt) {
        if (!isLegalTransition(node.status(), to)) {
            throw new IllegalStateTransitionException(node.taskId(), node.status(), to);
        }

        return node.withStatus(to, updatedAt);
    }
}
