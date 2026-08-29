package com.example.backend.workflow;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.tracing.TestTracing;
import com.example.backend.workflow.WorkflowTaskDispatcher.DispatchOutcome;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/**
 * Task 13.3: a workflow run is one trace -- a workflow.execute span with
 * one workflow.node child per node attempt, in real execution order, with
 * retries and failures visible on the spans.
 */
class WorkflowTracingTest {

    private static final Instant NOW = Instant.parse("2024-08-10T00:00:00Z");

    private final TestTracing tracing = new TestTracing();

    private static WorkflowNode node(String taskId, String... dependencies) {
        return WorkflowNode.pending(taskId, taskId, List.of(dependencies), "{}", NOW);
    }

    private Workflow run(WorkflowTaskDispatcher dispatcher, WorkflowNode... nodes) {
        Workflow workflow = new Workflow("wf-1", "forecast-pipeline", null, NOW, List.of(nodes));
        return new WorkflowExecutor(dispatcher, Clock.fixed(NOW, ZoneOffset.UTC), 3, tracing.spans())
                .execute(workflow);
    }

    private static String attribute(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }

    @Test
    void eachNodeAttemptIsAChildOfTheWorkflowSpanInExecutionOrder() {
        AtomicInteger validateCalls = new AtomicInteger();
        run(node -> node.taskId().equals("validate") && validateCalls.incrementAndGet() == 1
                        ? DispatchOutcome.transientFailure("store briefly unavailable")
                        : DispatchOutcome.success(node.taskId() + "-out"),
                node("get_data"), node("validate", "get_data"), node("run_forecast", "validate"));

        SpanData workflow = tracing.only("workflow.execute");
        assertFalse(workflow.getParentSpanContext().isValid(), "a run with nothing above it is its own trace");
        assertEquals("wf-1", attribute(workflow, "workflow.id"));
        assertNotEquals(StatusCode.ERROR, workflow.getStatus().getStatusCode());

        List<SpanData> nodes = tracing.named("workflow.node").stream()
                .sorted((a, b) -> Long.compare(a.getStartEpochNanos(), b.getStartEpochNanos()))
                .toList();
        assertTrue(nodes.stream().allMatch(n -> n.getParentSpanId().equals(workflow.getSpanId())));
        assertEquals(List.of("get_data", "validate", "validate", "run_forecast"),
                nodes.stream().map(n -> attribute(n, "workflow.task_id")).toList());

        SpanData failedValidate = nodes.get(1);
        assertEquals("RETRYING", attribute(failedValidate, "workflow.node_status"));
        assertEquals(StatusCode.ERROR, failedValidate.getStatus().getStatusCode());
        assertEquals("SUCCEEDED", attribute(nodes.get(2), "workflow.node_status"));
        assertNotEquals(StatusCode.ERROR, nodes.get(2).getStatus().getStatusCode());
    }

    @Test
    void aFailedNodeMarksItsSpanAndTheWorkflowSpanFailed() {
        run(node -> node.taskId().equals("get_data")
                        ? DispatchOutcome.permanentFailure("no data for region")
                        : DispatchOutcome.success(node.taskId() + "-out"),
                node("get_data"), node("run_forecast", "get_data"));

        SpanData failed = tracing.only("workflow.node");
        assertEquals("FAILED", attribute(failed, "workflow.node_status"));
        assertEquals("no data for region", failed.getStatus().getDescription());

        SpanData workflow = tracing.only("workflow.execute");
        assertEquals(StatusCode.ERROR, workflow.getStatus().getStatusCode());
        assertEquals(1L, workflow.getAttributes().get(AttributeKey.longKey("workflow.failed")));
        assertEquals(1L, workflow.getAttributes().get(AttributeKey.longKey("workflow.cancelled")),
                "run_forecast was cancelled, never dispatched, so it has no node span");
    }

    @Test
    void aWorkflowRunInsideAnotherSpanJoinsItsTrace() {
        tracing.spans().root("http post /workflows", () -> run(
                node -> DispatchOutcome.success(node.taskId() + "-out"), node("get_data")));

        SpanData http = tracing.only("http post /workflows");
        assertEquals(http.getSpanId(), tracing.only("workflow.execute").getParentSpanId());
    }
}
