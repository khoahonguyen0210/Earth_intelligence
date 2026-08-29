package com.example.backend.tracing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

class SpansTest {

    private static final Pattern W3C_TRACEPARENT = Pattern.compile("00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}");

    private final TestTracing tracing = new TestTracing();
    private final Spans spans = tracing.spans();

    @Test
    void aChildSpanOutsideAnyTraceRunsTheWorkUntraced() {
        String result = spans.child("forecast.store.find", () -> "done");

        assertEquals("done", result);
        assertTrue(tracing.finished().isEmpty(), "no orphan one-span trace");
    }

    @Test
    void aChildSpanInsideARootSpanIsItsChildInTheSameTrace() {
        spans.root("workflow.execute", () -> {
            spans.child("workflow.node", () -> {
            });
            return null;
        });

        SpanData root = tracing.only("workflow.execute");
        SpanData child = tracing.only("workflow.node");
        assertEquals(root.getTraceId(), child.getTraceId());
        assertEquals(root.getSpanId(), child.getParentSpanId());
        assertFalse(root.getParentSpanContext().isValid(), "root has no parent");
    }

    @Test
    void currentTraceParentIsTheCurrentSpansW3cHeaderAndNullOutsideATrace() {
        assertNull(spans.currentTraceParent());

        AtomicReference<String> traceParent = new AtomicReference<>();
        spans.root("forecast.job.submit", () -> {
            traceParent.set(spans.currentTraceParent());
            return null;
        });

        SpanData submit = tracing.only("forecast.job.submit");
        assertTrue(W3C_TRACEPARENT.matcher(traceParent.get()).matches(), traceParent.get());
        String flags = submit.getSpanContext().getTraceFlags().asHex();
        assertEquals("00-" + submit.getTraceId() + "-" + submit.getSpanId() + "-" + flags, traceParent.get());
    }

    @Test
    void aContinuedSpanJoinsTheTraceOfTheStoredTraceParent() {
        AtomicReference<String> traceParent = new AtomicReference<>();
        spans.root("forecast.job.submit", () -> {
            traceParent.set(spans.currentTraceParent());
            return null;
        });

        // Later, with nothing in scope -- as on the worker thread.
        spans.continued(traceParent.get(), "forecast.job.attempt", () -> spans.child("forecast.python", () -> {
        }));

        SpanData submit = tracing.only("forecast.job.submit");
        SpanData attempt = tracing.only("forecast.job.attempt");
        SpanData python = tracing.only("forecast.python");
        assertEquals(submit.getTraceId(), attempt.getTraceId());
        assertEquals(submit.getSpanId(), attempt.getParentSpanId());
        assertEquals(attempt.getSpanId(), python.getParentSpanId());
    }

    @Test
    void aContinuedSpanWithoutATraceParentStartsANewTrace() {
        spans.continued(null, "forecast.job.attempt", () -> {
        });
        spans.continued("not-a-traceparent", "forecast.job.attempt", () -> {
        });

        assertEquals(2, tracing.named("forecast.job.attempt").size());
        for (SpanData attempt : tracing.named("forecast.job.attempt")) {
            assertFalse(attempt.getParentSpanContext().isValid(), "no parent to continue");
        }
        assertNotEquals(tracing.finished().get(0).getTraceId(), tracing.finished().get(1).getTraceId());
    }

    @Test
    void tagsKeepTheirTypeAndAreIgnoredOutsideATrace() {
        spans.tag("ignored", "no span in scope");

        spans.root("span", () -> {
            spans.tag("text", "value");
            spans.tag("count", 3);
            spans.tag("millis", 4.25);
            spans.tag("flag", true);
            spans.tag("absent", null);
            return null;
        });

        SpanData span = tracing.only("span");
        assertEquals("value", span.getAttributes().get(AttributeKey.stringKey("text")));
        assertEquals(3L, span.getAttributes().get(AttributeKey.longKey("count")));
        assertEquals(4.25, span.getAttributes().get(AttributeKey.doubleKey("millis")));
        assertEquals(true, span.getAttributes().get(AttributeKey.booleanKey("flag")));
        assertNull(span.getAttributes().get(AttributeKey.stringKey("absent")));
    }

    @Test
    void failMarksTheSpanFailedWithTheMessageAndNoStackTrace() {
        spans.root("forecast.job.attempt", () -> {
            spans.fail("PYTHON_FAILED: invalid region");
            return null;
        });

        SpanData span = tracing.only("forecast.job.attempt");
        assertEquals(StatusCode.ERROR, span.getStatus().getStatusCode());
        assertEquals("PYTHON_FAILED: invalid region", span.getStatus().getDescription());
        String stackTrace = span.getEvents().getFirst().getAttributes()
                .get(AttributeKey.stringKey("exception.stacktrace"));
        assertFalse(stackTrace.contains("\tat "), "no meaningless stack frames: " + stackTrace);
    }

    @Test
    void anExceptionMarksTheSpanFailedEndsItAndPropagates() {
        IllegalStateException thrown = assertThrows(IllegalStateException.class,
                () -> spans.root("workflow.execute", () -> {
                    throw new IllegalStateException("boom");
                }));

        assertEquals("boom", thrown.getMessage());
        SpanData span = tracing.only("workflow.execute");
        assertEquals(StatusCode.ERROR, span.getStatus().getStatusCode());
        assertTrue(span.hasEnded());
    }

    @Test
    void noopTracesNothingAndStillRunsTheWork() {
        Spans noop = Spans.noop();

        assertEquals("done", noop.root("span", () -> "done"));
        assertNull(noop.currentTraceParent());
        noop.continued("00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01", "span", () -> {
        });
    }
}
