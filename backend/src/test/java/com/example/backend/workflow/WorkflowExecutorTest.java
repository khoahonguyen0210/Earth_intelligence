package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.workflow.WorkflowNode.Status;
import com.example.backend.workflow.WorkflowTaskDispatcher.DispatchOutcome;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WorkflowExecutorTest {

    private static final Instant NOW = Instant.parse("2024-08-10T00:00:00Z");

    /** Queues a scripted sequence of outcomes per task_id; records dispatch order. */
    private static class FakeDispatcher implements WorkflowTaskDispatcher {
        final Map<String, Deque<DispatchOutcome>> scripted = new HashMap<>();
        final List<String> dispatchedInOrder = new ArrayList<>();

        FakeDispatcher script(String taskId, DispatchOutcome... outcomes) {
            scripted.put(taskId, new ArrayDeque<>(List.of(outcomes)));
            return this;
        }

        @Override
        public DispatchOutcome dispatch(WorkflowNode node) {
            dispatchedInOrder.add(node.taskId());
            Deque<DispatchOutcome> queue = scripted.get(node.taskId());
            DispatchOutcome outcome = (queue != null && !queue.isEmpty())
                    ? queue.poll()
                    : DispatchOutcome.success(node.taskId() + "-output");
            return outcome;
        }
    }

    private static WorkflowNode node(String taskId, String... dependencies) {
        return WorkflowNode.pending(taskId, taskId, List.of(dependencies), "{}", NOW);
    }

    private static WorkflowExecutor executor(WorkflowTaskDispatcher dispatcher, int maxAttempts) {
        return new WorkflowExecutor(dispatcher, Clock.fixed(NOW, ZoneOffset.UTC), maxAttempts);
    }

    @Test
    void runsTheHandbooksLinearChainExampleToCompletion() {
        // get_data -> validate -> build_features -> run_forecast
        Workflow workflow = new Workflow(
                "wf-1",
                "forecast-pipeline",
                null,
                NOW,
                List.of(
                        node("get_data"),
                        node("validate", "get_data"),
                        node("build_features", "validate"),
                        node("run_forecast", "build_features")));
        FakeDispatcher dispatcher = new FakeDispatcher();

        Workflow result = executor(dispatcher, 3).execute(workflow);

        for (WorkflowNode resultNode : result.nodes()) {
            assertEquals(Status.SUCCEEDED, resultNode.status(), resultNode.taskId());
        }
        assertEquals(
                List.of("get_data", "validate", "build_features", "run_forecast"),
                dispatcher.dispatchedInOrder,
                "each node must dispatch only after its dependency has already succeeded");
    }

    @Test
    void runsTheHandbooksFanOutExampleToCompletion() {
        // run_forecast -> {get_result_evidence, generate_map}
        Workflow workflow = new Workflow(
                "wf-2",
                "forecast-with-evidence-and-map",
                null,
                NOW,
                List.of(
                        node("run_forecast"),
                        node("get_result_evidence", "run_forecast"),
                        node("generate_map", "run_forecast")));

        Workflow result = executor(new FakeDispatcher(), 3).execute(workflow);

        Map<String, Status> statusByTaskId = new HashMap<>();
        result.nodes().forEach(resultNode -> statusByTaskId.put(resultNode.taskId(), resultNode.status()));
        assertEquals(
                Map.of(
                        "run_forecast", Status.SUCCEEDED,
                        "get_result_evidence", Status.SUCCEEDED,
                        "generate_map", Status.SUCCEEDED),
                statusByTaskId);
    }

    @Test
    void aPermanentFailureCancelsEveryDownstreamDependent() {
        Workflow workflow = new Workflow(
                "wf-3",
                "middle-fails",
                null,
                NOW,
                List.of(
                        node("get_data"),
                        node("validate", "get_data"),
                        node("build_features", "validate"),
                        node("run_forecast", "build_features")));
        FakeDispatcher dispatcher = new FakeDispatcher()
                .script("validate", DispatchOutcome.permanentFailure("malformed data"));

        Workflow result = executor(dispatcher, 3).execute(workflow);

        Map<String, WorkflowNode> byTaskId = new HashMap<>();
        result.nodes().forEach(resultNode -> byTaskId.put(resultNode.taskId(), resultNode));

        assertEquals(Status.SUCCEEDED, byTaskId.get("get_data").status());
        assertEquals(Status.FAILED, byTaskId.get("validate").status());
        assertEquals("malformed data", byTaskId.get("validate").error());
        assertEquals(Status.CANCELLED, byTaskId.get("build_features").status());
        assertEquals(Status.CANCELLED, byTaskId.get("run_forecast").status());
        assertTrue(dispatcher.dispatchedInOrder.contains("get_data"));
        assertTrue(dispatcher.dispatchedInOrder.contains("validate"));
        assertTrue(
                !dispatcher.dispatchedInOrder.contains("build_features")
                        && !dispatcher.dispatchedInOrder.contains("run_forecast"),
                "a cancelled node must never actually be dispatched");
    }

    @Test
    void independentBranchesAreUnaffectedByASiblingsFailure() {
        Workflow workflow = new Workflow(
                "wf-4",
                "independent-branches",
                null,
                NOW,
                List.of(node("branch_a"), node("branch_b")));
        FakeDispatcher dispatcher =
                new FakeDispatcher().script("branch_a", DispatchOutcome.permanentFailure("boom"));

        Workflow result = executor(dispatcher, 3).execute(workflow);

        Map<String, Status> statusByTaskId = new HashMap<>();
        result.nodes().forEach(resultNode -> statusByTaskId.put(resultNode.taskId(), resultNode.status()));
        assertEquals(Status.FAILED, statusByTaskId.get("branch_a"));
        assertEquals(Status.SUCCEEDED, statusByTaskId.get("branch_b"));
    }

    @Test
    void aTransientFailureIsRetriedAndCanEventuallySucceed() {
        Workflow workflow = new Workflow("wf-5", "retry-then-succeed", null, NOW, List.of(node("a")));
        FakeDispatcher dispatcher = new FakeDispatcher()
                .script(
                        "a",
                        DispatchOutcome.transientFailure("network blip"),
                        DispatchOutcome.success("a-output"));

        Workflow result = executor(dispatcher, 3).execute(workflow);

        WorkflowNode a = result.nodes().get(0);
        assertEquals(Status.SUCCEEDED, a.status());
        assertEquals("a-output", a.outputRef());
        assertEquals(2, a.attempt());
        assertEquals(List.of("a", "a"), dispatcher.dispatchedInOrder);
    }

    @Test
    void aTransientFailureThatExhaustsMaxAttemptsEndsUpFailed() {
        Workflow workflow = new Workflow("wf-6", "retries-exhausted", null, NOW, List.of(node("a")));
        FakeDispatcher dispatcher = new FakeDispatcher()
                .script(
                        "a",
                        DispatchOutcome.transientFailure("blip 1"),
                        DispatchOutcome.transientFailure("blip 2"),
                        DispatchOutcome.transientFailure("blip 3"));

        Workflow result = executor(dispatcher, 2).execute(workflow);

        WorkflowNode a = result.nodes().get(0);
        assertEquals(Status.FAILED, a.status());
        assertEquals(2, a.attempt(), "must not exceed maxAttempts real dispatch calls");
        assertEquals(List.of("a", "a"), dispatcher.dispatchedInOrder);
    }

    @Test
    void aNodeAlreadyRunningAtTheStartOfExecuteIsTreatedAsAnInterruptedAttemptAndRetried() {
        // Task 8.4: a node stuck RUNNING can only be a leftover from a
        // process that crashed mid-dispatch -- execute() must resume it,
        // not leave it stuck forever.
        WorkflowNode orphanedRunning =
                WorkflowNode.pending("a", "a", List.of(), "{}", NOW).withStatus(Status.RUNNING, NOW);
        Workflow workflow = new Workflow("wf-9", "resumed-after-crash", null, NOW, List.of(orphanedRunning));

        Workflow result = executor(new FakeDispatcher(), 3).execute(workflow);

        WorkflowNode a = result.nodes().get(0);
        assertEquals(Status.SUCCEEDED, a.status());
        assertEquals(1, a.attempt());
    }

    @Test
    void executeRejectsAStructurallyInvalidWorkflow() {
        Workflow cyclic = new Workflow("wf-7", "cycle", null, NOW, List.of(node("a", "b"), node("b", "a")));

        assertThrows(IllegalArgumentException.class, () -> executor(new FakeDispatcher(), 3).execute(cyclic));
    }

    @Test
    void anEmptyWorkflowExecutesTriviallyToCompletion() {
        Workflow empty = new Workflow("wf-8", "empty", null, NOW, List.of());

        Workflow result = executor(new FakeDispatcher(), 3).execute(empty);

        assertEquals(List.of(), result.nodes());
    }
}
