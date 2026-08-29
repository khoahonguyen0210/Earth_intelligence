package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import com.example.backend.tracing.Spans;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

/** Task 13.2: every forecast meter, read back from a real Micrometer registry. */
class ForecastMetricsTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final Deque<String> queued = new ArrayDeque<>();
    private final ForecastQueue queue = new ForecastQueue() {
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
    };
    private final ForecastMetrics metrics = new ForecastMetrics(registry, queue);
    private ForecastStore store;

    @BeforeEach
    void setUpStore() {
        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        Map<String, ForecastEntity> backing = new HashMap<>();
        when(repository.save(any())).thenAnswer(invocation -> {
            ForecastEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));
        store = new ForecastStore(repository, new ObjectMapper(), Spans.noop());
    }

    private double gauge(String name) {
        return registry.get(name).gauge().value();
    }

    @Test
    void queueDepthGaugeReadsTheLiveQueueOnEveryScrape() {
        assertEquals(0.0, gauge("forecast.queue.depth"));

        queue.enqueue("a");
        queue.enqueue("b");

        assertEquals(2.0, gauge("forecast.queue.depth"));
    }

    @Test
    void queueDepthIsNaNNotZeroWhenTheQueueIsUnreachable() {
        SimpleMeterRegistry isolated = new SimpleMeterRegistry();
        new ForecastMetrics(isolated, new ForecastQueue() {
            @Override
            public void enqueue(String forecastId) {
            }

            @Override
            public Optional<String> dequeue() {
                return Optional.empty();
            }

            @Override
            public long size() {
                throw new IllegalStateException("redis down");
            }
        });

        assertTrue(Double.isNaN(isolated.get("forecast.queue.depth").gauge().value()));
    }

    @Test
    void successfulJobRecordsDurationStageTimingsAndBusyOnlyWhileRunning() {
        double[] busyDuringRun = new double[1];
        store.save(Forecast.pending("job-1", REQUEST, Instant.now(), null));
        queue.enqueue("job-1");
        ForecastRunner runner = request -> {
            busyDuringRun[0] = gauge("forecast.worker.busy");
            return ForecastOutcome.success(Map.of("ok", true), Map.of(
                    "data_load", 120.0, "model_fit", 800.0, "model_inference", 4.5, "total", 930.0,
                    "not_a_stage", 1.0));
        };

        new ForecastWorker(queue, store, runner, 3, SecretRedactor.of(), metrics, Spans.noop()).pollOnce();

        assertEquals(1.0, busyDuringRun[0]);
        assertEquals(0.0, gauge("forecast.worker.busy"));
        assertEquals(1, registry.get("forecast.job.duration").tag("outcome", "succeeded").timer().count());

        var inference = registry.get("forecast.python.stage.duration").tag("stage", "model_inference").timer();
        assertEquals(1, inference.count());
        assertEquals(4.5, inference.totalTime(TimeUnit.MILLISECONDS), 1e-6);
        assertNull(registry.find("forecast.python.stage.duration").tag("stage", "not_a_stage").timer(),
                "unknown stage names must not become new time series");
    }

    @Test
    void transientThenTerminalFailuresAreCountedSeparatelyByErrorCode() {
        store.save(Forecast.pending("job-2", REQUEST, Instant.now(), null));
        queue.enqueue("job-2");
        ForecastWorker worker = new ForecastWorker(queue, store,
                request -> ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT, "timed out"),
                2, SecretRedactor.of(), metrics, Spans.noop());

        worker.pollOnce(); // attempt 1: retried
        worker.pollOnce(); // attempt 2 of 2: terminal

        assertEquals(1.0, registry.get("forecast.job.failures")
                .tags("error_code", "PYTHON_TIMEOUT", "terminal", "false").counter().count());
        assertEquals(1.0, registry.get("forecast.job.failures")
                .tags("error_code", "PYTHON_TIMEOUT", "terminal", "true").counter().count());
        assertEquals(1, registry.get("forecast.job.duration").tag("outcome", "retry_scheduled").timer().count());
        assertEquals(1, registry.get("forecast.job.duration").tag("outcome", "failed").timer().count());
    }
}
