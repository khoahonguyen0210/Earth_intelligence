package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.workflow.WorkflowNode.Status;
import com.example.backend.workflow.WorkflowTaskDispatcher.DispatchOutcome;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class WorkflowPartialFailureIntegrationTest {

    @Autowired
    private WorkflowStore store;

    private static WorkflowNode node(String taskId, String... dependencies) {
        return WorkflowNode.pending(taskId, taskId, List.of(dependencies), "{}", Instant.now());
    }

    @Test
    void aFailureIsContainedToItsDependentsAndTheRestOfTheWorkflowCompletes() {
        String id = "wf-" + UUID.randomUUID();
        store.save(new Workflow(id, "forecast-pipeline", "partial failure", Instant.now(), List.of(
                node("get_data"),
                node("validate", "get_data"),
                node("build_features", "validate"),
                node("calculate_statistics", "validate"),
                node("run_forecast", "build_features"),
                node("get_result_evidence", "run_forecast"),
                node("generate_map", "run_forecast"))));

        List<String> dispatched = new ArrayList<>();
        WorkflowTaskDispatcher dispatcher = node -> {
            dispatched.add(node.taskId());
            if (node.taskId().equals("build_features") && node.attempt() == 0) {
                return DispatchOutcome.transientFailure("feature store briefly unavailable");
            }
            if (node.taskId().equals("run_forecast")) {
                return DispatchOutcome.permanentFailure("model rejected the input: no lookback coverage");
            }
            return DispatchOutcome.success(node.taskId() + "-out");
        };

        long started = System.nanoTime();
        Workflow finished = new WorkflowExecutor(dispatcher, Clock.systemUTC(), 3)
                .execute(store.find(id).orElseThrow());
        long elapsedMs = (System.nanoTime() - started) / 1_000_000;
        store.save(finished);

        Map<String, WorkflowNode> reloaded = store.find(id).orElseThrow().nodes().stream()
                .collect(Collectors.toMap(WorkflowNode::taskId, n -> n));

        // Recovered: the transient failure was retried once and succeeded.
        assertEquals(Status.SUCCEEDED, reloaded.get("build_features").status());
        assertEquals(2, reloaded.get("build_features").attempt());

        // Contained: the permanent failure fails its own node, once, with its reason ...
        assertEquals(Status.FAILED, reloaded.get("run_forecast").status());
        assertEquals(1, reloaded.get("run_forecast").attempt(), "a permanent failure is never retried");
        assertEquals("model rejected the input: no lookback coverage", reloaded.get("run_forecast").error());

        // ... and cancels only what depends on it, without dispatching it.
        for (String dependent : List.of("get_result_evidence", "generate_map")) {
            assertEquals(Status.CANCELLED, reloaded.get(dependent).status(), dependent);
            assertFalse(dispatched.contains(dependent), dependent + " must never run");
            assertNull(reloaded.get(dependent).outputRef(), dependent);
        }

        // Unaffected: the independent branch and the upstream nodes completed.
        for (String done : List.of("get_data", "validate", "calculate_statistics")) {
            assertEquals(Status.SUCCEEDED, reloaded.get(done).status(), done);
        }

        assertEquals(List.of("get_data", "validate", "build_features", "calculate_statistics",
                "build_features", "run_forecast"), dispatched);
        assertTrue(elapsedMs < 5_000, "retries are in-line, with no wait: " + elapsedMs + " ms");
    }
}
