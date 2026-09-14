package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import com.example.backend.region.RegionStore;
import com.example.backend.tracing.Spans;
import com.example.backend.tracing.TestTracing;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/**
 * One forecast's trace, HTTP -> job -> worker -> storage -> result, through
 * the real controller, store and worker and the real OpenTelemetry bridge
 * (TestTracing). The HTTP server span Spring creates in the running app is
 * stood in for by a root span around the controller call;
 * TracingIntegrationTest covers the real one.
 */
class ForecastTracingTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");
    private static final String SECRET = "firms-map-key-0123456789";

    private final TestTracing tracing = new TestTracing();
    private final Spans spans = tracing.spans();
    private final FakeQueue queue = new FakeQueue();
    private final ForecastStore store = newStore(spans);
    private final ForecastController controller = new ForecastController(queue, store, spans);

    private static class FakeQueue implements ForecastQueue {
        private final Deque<String> queued = new ArrayDeque<>();

        @Override
        public void enqueue(String forecastId) {
            queued.add(forecastId);
        }

        @Override
        public Optional<String> dequeue() {
            return Optional.ofNullable(queued.poll());
        }

        @Override
        public long size() {
            return queued.size();
        }

        @Override
        public boolean contains(String forecastId) {
            return queued.contains(forecastId);
        }
    }

    private static ForecastStore newStore(Spans spans) {
        return InMemoryForecasts.store(spans);
    }

    private ForecastWorker worker(ForecastRunner runner) {
        return new ForecastWorker(queue, store, runner, 3, SecretRedactor.of(SECRET),
                new ForecastMetrics(new SimpleMeterRegistry(), queue), spans, 0, RegionStore.noop());
    }

    /** Submits a forecast inside a stand-in for Spring's HTTP server span; returns the job id. */
    private String submitOverHttp() {
        return spans.root("http post /forecasts",
                () -> controller.createForecast(REQUEST, null).getBody().forecastId());
    }

    private static String attribute(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }

    private static long longAttribute(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.longKey(key));
    }

    private List<SpanData> childrenOf(SpanData parent) {
        return tracing.finished().stream()
                .filter(span -> span.getParentSpanId().equals(parent.getSpanId()))
                .toList();
    }

    @Test
    void aSucceededJobIsOneTraceFromTheHttpRequestToTheStoredResult() {
        String jobId = submitOverHttp();
        worker(request -> spans.child("forecast.python", () -> ForecastOutcome.success(Map.of("ok", true))))
                .pollOnce();

        SpanData http = tracing.only("http post /forecasts");
        SpanData submit = tracing.only("forecast.job.submit");
        SpanData attempt = tracing.only("forecast.job.attempt");
        SpanData python = tracing.only("forecast.python");

        // Every span of the job, request side and worker side, is one trace.
        assertTrue(tracing.finished().stream().allMatch(span -> span.getTraceId().equals(http.getTraceId())),
                "one trace: " + tracing.finished());

        // HTTP -> job: the submit span, with the pending row's write under it.
        // (The enqueue span is RedisForecastQueue's; this fake queue has none.)
        assertEquals(http.getSpanId(), submit.getParentSpanId());
        assertEquals(jobId, attribute(submit, "job.id"));
        SpanData pendingSave = childrenOf(submit).stream()
                .filter(span -> span.getName().equals("forecast.store.save"))
                .findFirst().orElseThrow();
        assertEquals("PENDING", attribute(pendingSave, "forecast.status"));

        // job -> worker: the attempt continues the submit span, across the queue.
        assertEquals(submit.getSpanId(), attempt.getParentSpanId());
        assertEquals(jobId, attribute(attempt, "job.id"));
        assertEquals(1, longAttribute(attempt, "job.attempt"));
        assertEquals("succeeded", attribute(attempt, "job.outcome"));
        assertNotEquals(StatusCode.ERROR, attempt.getStatus().getStatusCode());

        // worker -> Python and storage -> result. (The RUNNING transition is
        // the atomic claim, made before the attempt span opens -- untraced,
        // like the dequeue, so skipped duplicates cost no spans.)
        assertEquals(attempt.getSpanId(), python.getParentSpanId());
        List<String> savedStatuses = childrenOf(attempt).stream()
                .filter(span -> span.getName().equals("forecast.store.save"))
                .map(span -> attribute(span, "forecast.status"))
                .toList();
        assertEquals(List.of("SUCCEEDED"), savedStatuses);

        // The row carries the submit span's traceparent -- the link across the queue.
        assertTrue(store.find(jobId).orElseThrow().traceParent()
                .startsWith("00-" + submit.getTraceId() + "-" + submit.getSpanId() + "-"));
    }

    @Test
    void retriedAttemptsAreSiblingsUnderTheSubmitSpanAndTheFailedOneIsMarked() {
        submitOverHttp();
        AtomicInteger calls = new AtomicInteger();
        ForecastWorker worker = worker(request -> calls.incrementAndGet() == 1
                ? ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT, "timed out")
                : ForecastOutcome.success(Map.of("ok", true)));

        worker.pollOnce(); // attempt 1 -> RETRYING, re-enqueued
        worker.pollOnce(); // attempt 2 -> SUCCEEDED

        SpanData submit = tracing.only("forecast.job.submit");
        List<SpanData> attempts = tracing.named("forecast.job.attempt");
        assertEquals(2, attempts.size());
        assertTrue(attempts.stream().allMatch(attempt -> attempt.getParentSpanId().equals(submit.getSpanId())));

        SpanData first = attempts.stream().filter(a -> longAttribute(a, "job.attempt") == 1).findFirst().orElseThrow();
        SpanData second = attempts.stream().filter(a -> longAttribute(a, "job.attempt") == 2).findFirst().orElseThrow();
        assertEquals(StatusCode.ERROR, first.getStatus().getStatusCode());
        assertEquals("retry_scheduled", attribute(first, "job.outcome"));
        assertEquals("PYTHON_TIMEOUT", attribute(first, "error.code"));
        assertTrue(childrenOf(first).stream().anyMatch(span -> "RETRYING".equals(attribute(span, "forecast.status"))),
                "the RETRYING write belongs to the attempt that scheduled the retry");
        assertNotEquals(StatusCode.ERROR, second.getStatus().getStatusCode());
        assertEquals("succeeded", attribute(second, "job.outcome"));
    }

    @Test
    void aFailedAttemptsSpanCarriesTheErrorCodeAndRedactedTextNeverTheSecret() {
        submitOverHttp();
        worker(request -> ForecastOutcome.failure(ErrorCode.PYTHON_FAILED,
                "HTTPError for https://firms.modaps.eosdis.nasa.gov/api/area/csv/" + SECRET + "/VIIRS_SNPP_SP"))
                .pollOnce();

        SpanData attempt = tracing.only("forecast.job.attempt");
        assertEquals(StatusCode.ERROR, attempt.getStatus().getStatusCode());
        assertEquals("failed", attribute(attempt, "job.outcome"));
        assertEquals("PYTHON_FAILED", attribute(attempt, "error.code"));
        String description = attempt.getStatus().getDescription();
        assertTrue(description.startsWith("PYTHON_FAILED: HTTPError"), description);
        assertTrue(description.contains("***"), description);
        assertFalse(tracing.finished().toString().contains(SECRET), "the secret reached a span");
    }

    @Test
    void aJobStoredWithoutATraceParentStartsItsOwnTrace() {
        // A row written before tracing existed, or while nothing was traced.
        store.save(Forecast.pending("legacy-job", REQUEST, Instant.now()));
        tracing.finished(); // (untraced: no span was in scope for that save)
        queue.enqueue("legacy-job");

        worker(request -> ForecastOutcome.success(Map.of("ok", true))).pollOnce();

        SpanData attempt = tracing.only("forecast.job.attempt");
        assertFalse(attempt.getParentSpanContext().isValid(), "a new trace, not an error");
        assertEquals("legacy-job", attribute(attempt, "job.id"));
    }

    @Test
    void anIdleWorkerAndASkippedJobProduceNoSpans() {
        ForecastWorker worker = worker(request -> {
            throw new AssertionError("runner must not run");
        });

        worker.pollOnce(); // empty queue
        queue.enqueue("does-not-exist");
        worker.pollOnce(); // unknown id -> job_skipped

        assertTrue(tracing.finished().isEmpty(), "no traces for polling or skipping: " + tracing.finished());
    }
}
