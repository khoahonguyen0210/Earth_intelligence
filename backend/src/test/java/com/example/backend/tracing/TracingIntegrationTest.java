package com.example.backend.tracing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import io.micrometer.core.instrument.MeterRegistry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import java.util.function.Predicate;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.micrometer.tracing.test.autoconfigure.AutoConfigureTracing;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 13.3 end to end: the real application on a random port -- Spring's
 * own HTTP server span, the real Postgres row carrying the traceparent,
 * the real Redis queue, the scheduled worker thread and a real Python
 * subprocess (the timed stub) -- exporting through the production
 * OpenTelemetry pipeline into memory instead of OTLP. Needs the same
 * `docker compose up -d` stack as BackendApplicationTests.
 *
 * @AutoConfigureTracing: Spring Boot disables span export in tests by
 * default; this opts back in, so the exporter wiring under test is the
 * production one. @AutoConfigureMetrics likewise, so the check that
 * metrics are not pushed over OTLP runs against the real meter wiring.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureTracing
@AutoConfigureMetrics
@ExtendWith(OutputCaptureExtension.class)
class TracingIntegrationTest {

    private static final Duration WAIT = Duration.ofSeconds(60);

    @TestConfiguration
    static class InMemoryExport {
        @Bean
        InMemorySpanExporter inMemorySpanExporter() {
            return InMemorySpanExporter.create();
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("forecast.python.script-path",
                () -> Path.of("src", "test", "resources", "timed_forecast_stub.py").toAbsolutePath().toString());
        registry.add("forecast.python.working-directory", () -> ".");
        // Its own queue, so no other test context's worker takes the job.
        registry.add("forecast.queue.key", () -> "tracing-itest-" + UUID.randomUUID());
        registry.add("forecast.queue.poll-timeout-seconds", () -> "1");
        registry.add("management.opentelemetry.tracing.export.schedule-delay", () -> "100ms");
    }

    @LocalServerPort
    private int port;

    @Autowired
    private InMemorySpanExporter exporter;

    @Autowired
    private ApplicationContext context;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> send(HttpRequest.Builder request) throws Exception {
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private List<SpanData> spansOf(String traceId) {
        return exporter.getFinishedSpanItems().stream().filter(span -> span.getTraceId().equals(traceId)).toList();
    }

    private static SpanData one(List<SpanData> spans, Predicate<SpanData> matching, String what) {
        List<SpanData> found = spans.stream().filter(matching).toList();
        assertEquals(1, found.size(), what + " in " + spans.stream().map(SpanData::getName).toList());
        return found.getFirst();
    }

    private static String attribute(SpanData span, String key) {
        return span.getAttributes().get(AttributeKey.stringKey(key));
    }

    @Test
    void aForecastsTraceRunsFromTheHttpRequestThroughTheWorkerToTheStoredResult(CapturedOutput output)
            throws Exception {
        HttpResponse<String> created = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/forecasts"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"2024-08-15T10:00:00Z\"}")));
        assertEquals(201, created.statusCode(), created.body());
        String jobId = new ObjectMapper().readTree(created.body()).path("forecast_id").asString();

        // Wait for the worker to finish the job and its spans to be exported.
        Instant deadline = Instant.now().plus(WAIT);
        SpanData submit = null;
        List<SpanData> trace = List.of();
        while (Instant.now().isBefore(deadline)) {
            submit = exporter.getFinishedSpanItems().stream()
                    .filter(span -> span.getName().equals("forecast.job.submit") && jobId.equals(attribute(span, "job.id")))
                    .findFirst().orElse(null);
            trace = submit == null ? List.of() : spansOf(submit.getTraceId());
            if (trace.stream().anyMatch(span -> span.getName().equals("forecast.job.attempt"))) {
                break;
            }
            Thread.sleep(200);
        }
        assertTrue(trace.stream().anyMatch(span -> span.getName().equals("forecast.job.attempt")),
                "no finished attempt within " + WAIT + ": " + exporter.getFinishedSpanItems());

        // HTTP: Spring's own server span is the root.
        SpanData server = one(trace, span -> !span.getParentSpanContext().isValid(), "the root span");
        assertEquals("http post /forecasts", server.getName());
        assertEquals(server.getSpanId(), submit.getParentSpanId());

        // job: the pending row and the enqueue, under the submit span.
        SpanData pending = one(trace, span -> "PENDING".equals(attribute(span, "forecast.status")), "PENDING save");
        SpanData enqueue = one(trace, span -> span.getName().equals("forecast.queue.enqueue"), "enqueue");
        assertEquals(submit.getSpanId(), pending.getParentSpanId());
        assertEquals(submit.getSpanId(), enqueue.getParentSpanId());

        // worker: the attempt continued the trace from the traceparent on the row.
        SpanData attempt = one(trace, span -> span.getName().equals("forecast.job.attempt"), "attempt");
        assertEquals(submit.getSpanId(), attempt.getParentSpanId());
        assertEquals(jobId, attribute(attempt, "job.id"));
        assertEquals("succeeded", attribute(attempt, "job.outcome"));
        assertNotEquals(StatusCode.ERROR, attempt.getStatus().getStatusCode());

        // worker -> Python, storage -> result.
        SpanData python = one(trace, span -> span.getName().equals("forecast.python"), "python");
        assertEquals(attempt.getSpanId(), python.getParentSpanId());
        assertEquals(4.25, python.getAttributes().get(AttributeKey.doubleKey("python.model_inference_ms")));
        SpanData result = one(trace, span -> "SUCCEEDED".equals(attribute(span, "forecast.status")), "result save");
        assertEquals(attempt.getSpanId(), result.getParentSpanId());

        // The worker thread's log lines carry the request's trace id: logs
        // and traces join across the queue, which request_id alone cannot.
        JsonNode succeeded = Arrays.stream(output.getOut().split("\\R"))
                .filter(line -> line.contains("\"job_succeeded\"") && line.contains(jobId))
                .map(line -> new ObjectMapper().readTree(line))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no job_succeeded line for " + jobId));
        assertEquals(server.getTraceId(), succeeded.path("traceId").asString());
        assertEquals(attempt.getSpanId(), succeeded.path("spanId").asString());
    }

    @Test
    void anIdleWorkerExportsNoTraces() throws Exception {
        exporter.reset();

        Thread.sleep(3_000); // three blocking polls of an empty queue

        List<String> names = exporter.getFinishedSpanItems().stream().map(SpanData::getName).toList();
        assertTrue(names.isEmpty(), "idle polling must not create traces: " + names);
    }

    @Test
    void metricsStayPrometheusPullAndAreNotPushedOverOtlp() {
        List<String> registries = context.getBeansOfType(MeterRegistry.class).values().stream()
                .map(registry -> registry.getClass().getSimpleName())
                .toList();

        assertTrue(registries.contains("PrometheusMeterRegistry"), registries.toString());
        assertTrue(registries.stream().noneMatch(name -> name.startsWith("Otlp")), registries.toString());
    }
}
