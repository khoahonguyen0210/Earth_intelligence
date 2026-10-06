package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.workflow.WorkflowNode.Status;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class WorkflowStoreTest {

    @Autowired
    private WorkflowStore store;

    private static final Instant NOW = Instant.parse("2024-08-10T00:00:00Z");

    private static WorkflowNode node(String taskId, Status status, String... dependencies) {
        WorkflowNode pending = WorkflowNode.pending(taskId, taskId, List.of(dependencies), "{\"k\":\"v\"}", NOW);
        return status == Status.PENDING ? pending : pending.withStatus(status, NOW);
    }

    private static String freshId() {
        return "wf-" + UUID.randomUUID();
    }

    @Test
    void savingAndFindingAWorkflowRoundTripsEveryField() {
        String id = freshId();
        Workflow workflow = new Workflow(
                id,
                "forecast-pipeline",
                "a real pipeline",
                NOW,
                List.of(
                        node("get_data", Status.SUCCEEDED),
                        node("validate", Status.RUNNING, "get_data")));

        store.save(workflow);
        Optional<Workflow> reloaded = store.find(id);

        assertTrue(reloaded.isPresent());
        assertEquals(workflow.id(), reloaded.get().id());
        assertEquals(workflow.name(), reloaded.get().name());
        assertEquals(workflow.description(), reloaded.get().description());
        assertEquals(workflow.createdAt(), reloaded.get().createdAt());
        assertEquals(workflow.nodes().size(), reloaded.get().nodes().size());

        Map<String, WorkflowNode> reloadedByTaskId = new java.util.HashMap<>();
        reloaded.get().nodes().forEach(n -> reloadedByTaskId.put(n.taskId(), n));

        WorkflowNode reloadedValidate = reloadedByTaskId.get("validate");
        assertEquals(Status.RUNNING, reloadedValidate.status());
        assertEquals(List.of("get_data"), reloadedValidate.dependencies());
        assertEquals("{\"k\":\"v\"}", reloadedValidate.inputRef());
    }

    @Test
    void findingAnUnknownWorkflowIdReturnsEmpty() {
        assertEquals(Optional.empty(), store.find(freshId()));
    }

    @Test
    void savingTwiceUpdatesTheSameRowsRatherThanDuplicating() {
        String id = freshId();
        Workflow first = new Workflow(id, "wf", null, NOW, List.of(node("a", Status.PENDING)));
        store.save(first);

        Workflow updated = new Workflow(id, "wf", null, NOW, List.of(node("a", Status.SUCCEEDED)));
        store.save(updated);

        Optional<Workflow> reloaded = store.find(id);
        assertEquals(1, reloaded.get().nodes().size());
        assertEquals(Status.SUCCEEDED, reloaded.get().nodes().get(0).status());
    }

    @Test
    void aWorkflowSavedMidRunCanBeReloadedAndResumedToCompletionAfterASimulatedRestart() {
        String id = freshId();
        Workflow midRun = new Workflow(
                id,
                "resumable-pipeline",
                null,
                NOW,
                List.of(
                        node("get_data", Status.SUCCEEDED),
                        node("validate", Status.RUNNING, "get_data"),
                        node("build_features", Status.PENDING, "validate"),
                        node("run_forecast", Status.PENDING, "build_features")));
        store.save(midRun);

        Workflow recovered = store.find(id).orElseThrow();
        WorkflowExecutor freshExecutorAfterRestart =
                new WorkflowExecutor(node -> WorkflowTaskDispatcher.DispatchOutcome.success(node.taskId() + "-out"),
                        Clock.fixed(NOW, ZoneOffset.UTC), 3);

        Workflow completed = freshExecutorAfterRestart.execute(recovered);

        for (WorkflowNode resultNode : completed.nodes()) {
            assertEquals(Status.SUCCEEDED, resultNode.status(), resultNode.taskId());
        }
    }
}
