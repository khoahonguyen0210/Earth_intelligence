package com.example.backend.forecast;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Task 6.5's worker: the consumer side of ForecastQueue. pollOnce is
 * scheduled back-to-back (fixedDelay); since ForecastQueue.dequeue
 * already blocks for forecast.queue.poll-timeout-seconds when the queue
 * is empty, this is a continuous blocking-poll loop rather than a
 * busy-wait, without needing a dedicated thread.
 *
 * A dequeued id whose forecast is missing or not PENDING/RETRYING
 * (already terminal, or a stale duplicate entry) is skipped rather than
 * reprocessed.
 *
 * Task 6.6: a transient outcome (ForecastRunner couldn't reach its
 * dependency, or timed out -- see PythonForecastRunner) is retried by
 * re-enqueueing the same id, up to forecast.worker.max-attempts, moving
 * through RETRYING in between. A permanent outcome (the request/data
 * itself is the problem) goes straight to FAILED on the first attempt,
 * never retried. See docs/forecast-retry-and-idempotency.md.
 */
@Component
public class ForecastWorker {

    private final ForecastQueue queue;
    private final ForecastStore store;
    private final ForecastRunner runner;
    private final int maxAttempts;

    public ForecastWorker(
            ForecastQueue queue,
            ForecastStore store,
            ForecastRunner runner,
            @Value("${forecast.worker.max-attempts}") int maxAttempts) {
        this.queue = queue;
        this.store = store;
        this.runner = runner;
        this.maxAttempts = maxAttempts;
    }

    @Scheduled(fixedDelay = 100)
    public void pollOnce() {
        queue.dequeue().ifPresent(this::process);
    }

    private void process(String forecastId) {
        store.find(forecastId)
                .filter(forecast -> forecast.status() == Forecast.Status.PENDING
                        || forecast.status() == Forecast.Status.RETRYING)
                .ifPresent(forecast -> {
                    store.save(forecast.withStatus(Forecast.Status.RUNNING));

                    ForecastOutcome outcome = runner.run(forecast.request());
                    Forecast attempted = forecast.withAttempts(forecast.attempts() + 1);

                    if (!outcome.success() && outcome.transientFailure() && attempted.attempts() < maxAttempts) {
                        store.save(attempted.withStatus(Forecast.Status.RETRYING));
                        queue.enqueue(forecastId);
                    } else {
                        store.save(attempted.withOutcome(outcome));
                    }
                });
    }
}
