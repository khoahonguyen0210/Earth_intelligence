package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class ForecastWorkerTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");

    private static final int DEFAULT_MAX_ATTEMPTS = 3;

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
    }

    private static ForecastStore newStore() {
        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        Map<String, ForecastEntity> backing = new HashMap<>();

        when(repository.save(any())).thenAnswer(invocation -> {
            ForecastEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));

        return new ForecastStore(repository, new ObjectMapper());
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
        ForecastWorker worker = new ForecastWorker(queue, store, runner, DEFAULT_MAX_ATTEMPTS);

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
                queue, store, request -> ForecastOutcome.failure("boom"), DEFAULT_MAX_ATTEMPTS);

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
        }, DEFAULT_MAX_ATTEMPTS);

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
        }, DEFAULT_MAX_ATTEMPTS);

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
        }, DEFAULT_MAX_ATTEMPTS);

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
                ? ForecastOutcome.transientFailure("temporarily unavailable")
                : ForecastOutcome.success(Map.of("model_version", "v1"));
        ForecastWorker worker = new ForecastWorker(queue, store, runner, DEFAULT_MAX_ATTEMPTS);

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
                queue, store, request -> ForecastOutcome.transientFailure("still unavailable"), 2);

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
                queue, store, request -> ForecastOutcome.failure("invalid region"), DEFAULT_MAX_ATTEMPTS);

        worker.pollOnce();

        Forecast finished = store.find("job-1").orElseThrow();
        assertEquals(Forecast.Status.FAILED, finished.status());
        assertEquals(1, finished.attempts());
        assertTrue(queue.dequeue().isEmpty(), "a permanent failure must never be retried");
    }
}
