package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;

import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import com.example.backend.tracing.Spans;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.data.redis.RedisConnectionFailureException;
import tools.jackson.databind.ObjectMapper;

class ForecastWorkerTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private static final int DEFAULT_MAX_ATTEMPTS = 3;
    private static final SecretRedactor NO_SECRETS = SecretRedactor.of();
    private static final ForecastMetrics METRICS = new ForecastMetrics(new SimpleMeterRegistry(), new FakeQueue());

    private static class FakeQueue implements ForecastQueue {
        private final Deque<String> queued = new ArrayDeque<>();

        void seed(String forecastId) {
            queued.add(forecastId);
        }

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

    private static ForecastStore newStore() {
        return InMemoryForecasts.store(Spans.noop());
    }

    /** Captures the forecast's status in the store at the moment the runner is invoked. */
    private static class ObservingRunner implements ForecastRunner {
        private final ForecastStore store;
        private final String forecastId;
        private final ForecastOutcome outcome;
        private Forecast.Status statusDuringRun;

        ObservingRunner(ForecastStore store, String forecastId, ForecastOutcome outcome) {
            this.store = store;
            this.forecastId = forecastId;
            this.outcome = outcome;
        }

        @Override
        public ForecastOutcome run(ForecastRequest request) {
            statusDuringRun = store.find(forecastId).orElseThrow().status();
            return outcome;
        }
    }

    @Test
    void processesAPendingForecastThroughToSucceeded() {
        ForecastStore store = newStore();
        Forecast pending = Forecast.pending("job-1", REQUEST, Instant.now());
        store.save(pending);

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        ObservingRunner runner = new ObservingRunner(store, "job-1", ForecastOutcome.success(Map.of("model_version", "v1")));
        ForecastWorker worker = new ForecastWorker(queue, store, runner, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        assertEquals(Forecast.Status.RUNNING, runner.statusDuringRun);
        assertEquals(Forecast.Status.SUCCEEDED, store.find("job-1").orElseThrow().status());
        assertEquals(Map.of("model_version", "v1"), store.find("job-1").orElseThrow().result());
    }

    @Test
    void processesAPendingForecastThroughToFailed() {
        ForecastStore store = newStore();
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        ForecastWorker worker = new ForecastWorker(
                queue, store, request -> ForecastOutcome.failure(ErrorCode.PYTHON_FAILED, "boom"),
                DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        Forecast finished = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.FAILED, finished.status());
        assertEquals("boom", finished.error());
    }

    @Test
    void doesNothingWhenTheQueueIsEmpty() {
        ForecastStore store = newStore();
        ForecastWorker worker = new ForecastWorker(new FakeQueue(), store, request -> {
            throw new AssertionError("runner should not be invoked when the queue is empty");
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();
    }

    @Test
    void skipsAForecastThatIsNoLongerPending() {
        ForecastStore store = newStore();
        store.save(Forecast.from("job-1", REQUEST, Instant.now(), ForecastOutcome.success(Map.of("model_version", "v1"))));

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        ForecastWorker worker = new ForecastWorker(queue, store, request -> {
            throw new AssertionError("runner should not reprocess an already-terminal forecast");
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        assertEquals(Forecast.Status.SUCCEEDED, store.find("job-1").orElseThrow().status());
    }

    @Test
    void skipsAnIdThatIsNotInTheStore() {
        ForecastStore store = newStore();
        FakeQueue queue = new FakeQueue();
        queue.seed("does-not-exist");
        ForecastWorker worker = new ForecastWorker(queue, store, request -> {
            throw new AssertionError("runner should not be invoked for an unknown id");
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        assertFalse(store.find("does-not-exist").isPresent());
    }

    @Test
    void retriesATransientFailureAndSucceedsOnTheSecondAttempt() {
        ForecastStore store = newStore();
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        AtomicInteger calls = new AtomicInteger();
        ForecastRunner runner = request -> calls.incrementAndGet() == 1
                ? ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT, "temporarily unavailable")
                : ForecastOutcome.success(Map.of("model_version", "v1"));
        ForecastWorker worker = new ForecastWorker(queue, store, runner, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();
        Forecast afterFirstAttempt = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.RETRYING, afterFirstAttempt.status());
        assertEquals(1, afterFirstAttempt.attempts());
        assertTrue(queue.dequeue().isPresent(), "a transient failure must re-enqueue the job");

        queue.seed("job-1");
        worker.pollOnce();
        Forecast afterSecondAttempt = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.SUCCEEDED, afterSecondAttempt.status());
        assertEquals(2, afterSecondAttempt.attempts());
    }

    @Test
    void exhaustsRetriesOnRepeatedTransientFailureAndFails() {
        ForecastStore store = newStore();
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        ForecastWorker worker = new ForecastWorker(
                queue, store, request -> ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT, "still unavailable"),
                2, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce(); // attempt 1/2 -> RETRYING, worker re-enqueues it itself
        worker.pollOnce(); // attempt 2/2 -> attempts (2) is not < maxAttempts (2) -> FAILED

        Forecast finished = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.FAILED, finished.status());
        assertEquals(2, finished.attempts());
        assertTrue(queue.dequeue().isEmpty(), "exhausted retries must not re-enqueue a third attempt");
    }

    @Test
    void doesNotRetryAPermanentFailureEvenOnTheFirstAttempt() {
        ForecastStore store = newStore();
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));

        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        ForecastWorker worker = new ForecastWorker(
                queue, store, request -> ForecastOutcome.failure(ErrorCode.PYTHON_FAILED, "invalid region"),
                DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        Forecast finished = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.FAILED, finished.status());
        assertEquals(1, finished.attempts());
        assertTrue(queue.dequeue().isEmpty(), "a permanent failure must never be retried");
    }

    // Task 13.5: reliability -- docs/reliability-tests.md.

    @Test
    void aDuplicateQueueEntryNeverRunsAJobTwice() {
        ForecastStore store = newStore();
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));
        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        queue.seed("job-1"); // e.g. re-enqueued by recovery while a worker already held it
        AtomicInteger runs = new AtomicInteger();
        ForecastWorker worker = new ForecastWorker(queue, store, request -> {
            runs.incrementAndGet();
            return ForecastOutcome.success(Map.of("ok", true));
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();
        worker.pollOnce();

        assertEquals(1, runs.get(), "the second entry's claim must fail");
        assertEquals(Forecast.Status.SUCCEEDED, store.find("job-1").orElseThrow().status());
    }

    @Test
    void aQueueOutageNeverEscapesThePollLoop() {
        ForecastQueue down = new FakeQueue() {
            @Override
            public Optional<String> dequeue() {
                throw new RedisConnectionFailureException("redis down");
            }
        };
        ForecastWorker worker = new ForecastWorker(down, newStore(), request -> {
            throw new AssertionError("nothing to run");
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();
        worker.pollOnce();
    }

    @Test
    void aDatabaseOutageMidJobLeavesTheJobRunningForRecoveryNotLost() {
        ForecastJpaRepository repository = InMemoryForecasts.repository();
        ForecastStore store = new ForecastStore(repository, new ObjectMapper(), Spans.noop());
        store.save(Forecast.pending("job-1", REQUEST, Instant.now()));
        FakeQueue queue = new FakeQueue();
        queue.seed("job-1");
        // Postgres goes away while the Python attempt runs: the result
        // write fails.
        ForecastWorker worker = new ForecastWorker(queue, store, request -> {
            doThrow(new DataAccessResourceFailureException("db down")).when(repository).save(any());
            return ForecastOutcome.success(Map.of("ok", true));
        }, DEFAULT_MAX_ATTEMPTS, NO_SECRETS, METRICS, Spans.noop(), 0);

        worker.pollOnce();

        assertEquals(Forecast.Status.RUNNING, store.find("job-1").orElseThrow().status(),
                "left RUNNING for ForecastRecovery to find, not dropped or marked failed");
    }
}
