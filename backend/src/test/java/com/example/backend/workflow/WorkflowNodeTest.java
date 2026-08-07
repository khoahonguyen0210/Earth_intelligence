package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class WorkflowNodeTest {

    @Test
    void pendingStartsAtStatusPendingWithZeroAttemptsAndNoOutputOrError() {
        Instant now = Instant.parse("2024-08-10T00:00:00Z");

        WorkflowNode node = WorkflowNode.pending("get_data", "get_data", List.of(), "{}", now);

        assertEquals(WorkflowNode.Status.PENDING, node.status());
        assertEquals(0, node.attempt());
        assertEquals(now, node.createdAt());
        assertEquals(now, node.updatedAt());
        assertEquals(List.of(), node.dependencies());
    }

    @Test
    void dependenciesIsDefensivelyCopiedAndImmutable() {
        Instant now = Instant.parse("2024-08-10T00:00:00Z");
        List<String> mutable = new java.util.ArrayList<>(List.of("a"));

        WorkflowNode node = WorkflowNode.pending("b", "calculate_statistics", mutable, "{}", now);
        mutable.add("c");

        assertEquals(List.of("a"), node.dependencies());
        assertThrows(UnsupportedOperationException.class, () -> node.dependencies().add("d"));
    }

    @Test
    void withStatusChangesOnlyStatusAndUpdatedAt() {
        Instant createdAt = Instant.parse("2024-08-10T00:00:00Z");
        Instant updatedAt = Instant.parse("2024-08-10T00:05:00Z");
        WorkflowNode node = WorkflowNode.pending("a", "get_data", List.of(), "{}", createdAt);

        WorkflowNode running = node.withStatus(WorkflowNode.Status.RUNNING, updatedAt);

        assertEquals(WorkflowNode.Status.RUNNING, running.status());
        assertEquals(updatedAt, running.updatedAt());
        assertEquals(createdAt, running.createdAt());
        assertEquals(node.taskId(), running.taskId());
    }

    @Test
    void withOutcomeSetsStatusOutputRefAndError() {
        Instant createdAt = Instant.parse("2024-08-10T00:00:00Z");
        Instant updatedAt = Instant.parse("2024-08-10T00:05:00Z");
        WorkflowNode node = WorkflowNode.pending("a", "get_data", List.of(), "{}", createdAt);

        WorkflowNode succeeded =
                node.withOutcome(WorkflowNode.Status.SUCCEEDED, "{\"record_count\": 5}", null, updatedAt);
        WorkflowNode failed = node.withOutcome(WorkflowNode.Status.FAILED, null, "boom", updatedAt);

        assertEquals(WorkflowNode.Status.SUCCEEDED, succeeded.status());
        assertEquals("{\"record_count\": 5}", succeeded.outputRef());
        assertEquals(WorkflowNode.Status.FAILED, failed.status());
        assertEquals("boom", failed.error());
    }

    @Test
    void withAttemptIncrementsAttemptOnly() {
        Instant createdAt = Instant.parse("2024-08-10T00:00:00Z");
        Instant updatedAt = Instant.parse("2024-08-10T00:05:00Z");
        WorkflowNode node = WorkflowNode.pending("a", "run_forecast", List.of(), "{}", createdAt);

        WorkflowNode retried = node.withAttempt(1, updatedAt);

        assertEquals(1, retried.attempt());
        assertEquals(WorkflowNode.Status.PENDING, retried.status());
    }

    @Test
    void requiresNonNullTaskIdTaskTypeStatusAndTimestamps() {
        Instant now = Instant.parse("2024-08-10T00:00:00Z");

        assertThrows(
                NullPointerException.class,
                () -> new WorkflowNode(null, "get_data", List.of(), WorkflowNode.Status.PENDING, 0, "{}", null, now, now, null));
        assertThrows(
                NullPointerException.class,
                () -> new WorkflowNode("a", null, List.of(), WorkflowNode.Status.PENDING, 0, "{}", null, now, now, null));
        assertThrows(
                NullPointerException.class,
                () -> new WorkflowNode("a", "get_data", List.of(), null, 0, "{}", null, now, now, null));
    }
}
