package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.workflow.WorkflowNode.Status;
import java.time.Instant;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class WorkflowStateMachineTest {

    private static final Instant NOW = Instant.parse("2024-08-10T00:00:00Z");

    private static final Set<List<Status>> LEGAL_EDGES = Set.of(
            List.of(Status.PENDING, Status.READY),
            List.of(Status.PENDING, Status.CANCELLED),
            List.of(Status.READY, Status.RUNNING),
            List.of(Status.READY, Status.CANCELLED),
            List.of(Status.RUNNING, Status.SUCCEEDED),
            List.of(Status.RUNNING, Status.FAILED),
            List.of(Status.RUNNING, Status.RETRYING),
            List.of(Status.RUNNING, Status.CANCELLED),
            List.of(Status.RETRYING, Status.RUNNING),
            List.of(Status.RETRYING, Status.CANCELLED));

    @Test
    void everyStateStatePairMatchesTheDeclaredTransitionTable() {
        for (Status from : Status.values()) {
            for (Status to : Status.values()) {
                boolean expectedLegal = LEGAL_EDGES.contains(List.of(from, to));
                assertEquals(
                        expectedLegal,
                        WorkflowStateMachine.isLegalTransition(from, to),
                        () -> from + " -> " + to);
            }
        }
    }

    @Test
    void terminalStatesHaveNoLegalOutgoingTransitions() {
        for (Status terminal : EnumSet.of(Status.SUCCEEDED, Status.FAILED, Status.CANCELLED)) {
            assertTrue(WorkflowStateMachine.isTerminal(terminal));
            assertEquals(Set.of(), WorkflowStateMachine.legalNextStates(terminal));
        }
    }

    @Test
    void nonTerminalStatesAreNotTerminal() {
        for (Status nonTerminal : EnumSet.of(Status.PENDING, Status.READY, Status.RUNNING, Status.RETRYING)) {
            assertFalse(WorkflowStateMachine.isTerminal(nonTerminal));
        }
    }

    @Test
    void aNodeCanBeCancelledFromEveryNonTerminalState() {
        for (Status nonTerminal : EnumSet.of(Status.PENDING, Status.READY, Status.RUNNING, Status.RETRYING)) {
            assertTrue(WorkflowStateMachine.isLegalTransition(nonTerminal, Status.CANCELLED));
        }
    }

    @Test
    void pendingNeverGoesStraightToRunning() {
        assertFalse(WorkflowStateMachine.isLegalTransition(Status.PENDING, Status.RUNNING));
    }

    @Test
    void retryingReentersAtRunningNotReady() {
        assertTrue(WorkflowStateMachine.isLegalTransition(Status.RETRYING, Status.RUNNING));
        assertFalse(WorkflowStateMachine.isLegalTransition(Status.RETRYING, Status.READY));
    }

    @Test
    void transitionAppliesALegalChangeAndReturnsAnUpdatedNode() {
        WorkflowNode pending = WorkflowNode.pending("a", "get_data", List.of(), "{}", NOW);
        Instant updatedAt = NOW.plusSeconds(60);

        WorkflowNode ready = WorkflowStateMachine.transition(pending, Status.READY, updatedAt);

        assertEquals(Status.READY, ready.status());
        assertEquals(updatedAt, ready.updatedAt());
        assertEquals(Status.PENDING, pending.status(), "the original node is unchanged (immutable record)");
    }

    @Test
    void transitionRejectsAnIllegalChange() {
        WorkflowNode pending = WorkflowNode.pending("a", "get_data", List.of(), "{}", NOW);

        IllegalStateTransitionException exception = assertThrows(
                IllegalStateTransitionException.class,
                () -> WorkflowStateMachine.transition(pending, Status.RUNNING, NOW));

        assertTrue(exception.getMessage().contains("'a'"));
        assertTrue(exception.getMessage().contains("PENDING"));
        assertTrue(exception.getMessage().contains("RUNNING"));
    }

    @Test
    void transitionRejectsAnyChangeOutOfATerminalState() {
        WorkflowNode succeeded =
                WorkflowStateMachine.transition(
                        WorkflowStateMachine.transition(
                                WorkflowStateMachine.transition(
                                        WorkflowNode.pending("a", "get_data", List.of(), "{}", NOW),
                                        Status.READY,
                                        NOW),
                                Status.RUNNING,
                                NOW),
                        Status.SUCCEEDED,
                        NOW);

        assertThrows(
                IllegalStateTransitionException.class,
                () -> WorkflowStateMachine.transition(succeeded, Status.RUNNING, NOW));
    }
}
