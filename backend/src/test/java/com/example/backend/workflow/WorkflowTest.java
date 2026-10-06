package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class WorkflowTest {

    private static final Instant NOW = Instant.parse("2024-08-10T00:00:00Z");

    private static WorkflowNode node(String taskId, String... dependencies) {
        return WorkflowNode.pending(taskId, "calculate_statistics", List.of(dependencies), "{}", NOW);
    }

    @Test
    void validLinearChainHasNoErrors() {
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

        assertEquals(List.of(), workflow.validate());
    }

    @Test
    void validFanOutHasNoErrors() {
        Workflow workflow = new Workflow(
                "wf-2",
                "forecast-with-evidence-and-map",
                null,
                NOW,
                List.of(
                        node("run_forecast"),
                        node("get_result_evidence", "run_forecast"),
                        node("generate_map", "run_forecast")));

        assertEquals(List.of(), workflow.validate());
    }

    @Test
    void flagsDuplicateTaskIds() {
        Workflow workflow = new Workflow("wf-3", "dup", null, NOW, List.of(node("a"), node("a")));

        List<String> errors = workflow.validate();

        assertTrue(errors.stream().anyMatch(error -> error.contains("duplicate task_id")));
    }

    @Test
    void flagsSelfDependency() {
        Workflow workflow = new Workflow("wf-4", "self-dep", null, NOW, List.of(node("a", "a")));

        List<String> errors = workflow.validate();

        assertTrue(errors.stream().anyMatch(error -> error.contains("depends on itself")));
    }

    @Test
    void flagsDependencyOnAnUnknownTask() {
        Workflow workflow = new Workflow("wf-5", "missing-dep", null, NOW, List.of(node("a", "ghost")));

        List<String> errors = workflow.validate();

        assertTrue(errors.stream().anyMatch(error -> error.contains("unknown task 'ghost'")));
    }

    @Test
    void flagsATwoNodeCycle() {
        Workflow workflow =
                new Workflow("wf-6", "cycle", null, NOW, List.of(node("a", "b"), node("b", "a")));

        List<String> errors = workflow.validate();

        assertTrue(errors.stream().anyMatch(error -> error.contains("cycle")));
    }

    @Test
    void flagsALongerCycle() {
        Workflow workflow = new Workflow(
                "wf-7",
                "longer-cycle",
                null,
                NOW,
                List.of(node("a", "c"), node("b", "a"), node("c", "b")));

        List<String> errors = workflow.validate();

        assertTrue(errors.stream().anyMatch(error -> error.contains("cycle")));
    }

    @Test
    void emptyWorkflowHasNoErrors() {
        Workflow workflow = new Workflow("wf-8", "empty", null, NOW, List.of());

        assertEquals(List.of(), workflow.validate());
    }

    @Test
    void nodesIsDefensivelyCopiedAndImmutable() {
        List<WorkflowNode> mutable = new java.util.ArrayList<>(List.of(node("a")));

        Workflow workflow = new Workflow("wf-9", "defensive-copy", null, NOW, mutable);
        mutable.add(node("b"));

        assertEquals(1, workflow.nodes().size());
        org.junit.jupiter.api.Assertions.assertThrows(
                UnsupportedOperationException.class, () -> workflow.nodes().add(node("c")));
    }
}
