package com.example.backend.forecast;

import com.example.backend.logging.SecretRedactor;
import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * The consumer side of ForecastQueue. pollOnce is scheduled
 * back-to-back (fixedDelay); since ForecastQueue.dequeue already blocks
 * for forecast.queue.poll-timeout-seconds when the queue is empty, this
 * is a continuous blocking-poll loop rather than a busy-wait, without
 * needing a dedicated thread.
 *
 * A dequeued id whose forecast is missing or not PENDING/RETRYING
 * (already terminal, or a stale duplicate entry) is skipped rather than
 * reprocessed.
 *
 * A transient outcome (ForecastRunner couldn't reach its dependency, or
 * timed out -- see PythonForecastRunner) is retried by re-enqueueing the
 * same id, up to forecast.worker.max-attempts, moving through RETRYING
 * in between. A permanent outcome (the request/data itself is the
 * problem) goes straight to FAILED on the first attempt, never retried.
 * See docs/forecast-retry-and-idempotency.md.
 *
 * Every log line written while a job is processed carries `job_id`
 * (MDC), and each attempt ends in exactly one of the job_succeeded /
 * job_retry_scheduled / job_failed events, with the attempt number,
 * duration and, on failure, the error code and the redacted error text.
 *
 * The same outcomes feed ForecastMetrics -- attempt duration by
 * outcome, failures by error code, the Python stage timings, and the
 * busy gauge around each attempt (docs/metrics.md).
 *
 * Each attempt is a `forecast.job.attempt` span continuing the trace of
 * the request that submitted the job (its traceparent is on the
 * forecast row), so the Python run and the store writes below it --
 * including the one that records the result -- belong to that request's
 * trace, and so do this attempt's log lines (docs/tracing.md). A failed
 * attempt's span is marked failed with the error code and the same
 * redacted text the log line gets.
 */
@Component
public class ForecastWorker {

    public static final String MDC_JOB_ID = "job_id";

    private static final Logger log = LoggerFactory.getLogger(ForecastWorker.class);

    private final ForecastQueue queue;
    private final ForecastStore store;
    private final ForecastRunner runner;
    private final int maxAttempts;
    private final SecretRedactor redactor;
    private final ForecastMetrics metrics;
    private final Spans spans;
    private final Duration errorBackoff;
    private volatile boolean dependencyDown;

    public ForecastWorker(
            ForecastQueue queue,
            ForecastStore store,
            ForecastRunner runner,
            @Value("${forecast.worker.max-attempts}") int maxAttempts,
            SecretRedactor redactor,
            ForecastMetrics metrics,
            Spans spans,
            @Value("${forecast.worker.error-backoff-ms}") long errorBackoffMs) {
        this.queue = queue;
        this.store = store;
        this.runner = runner;
        this.maxAttempts = maxAttempts;
        this.redactor = redactor;
        this.metrics = metrics;
        this.spans = spans;
        this.errorBackoff = Duration.ofMillis(errorBackoffMs);
    }

    @Scheduled(fixedDelay = 100)
    public void pollOnce() {
        Optional<String> dequeued;
        try {
            dequeued = queue.dequeue();
        } catch (DataAccessException e) {
            dependencyUnavailable("dequeue", e);
            return;
        }
        dependencyAvailable();
        dequeued.ifPresent(this::process);
    }

    /**
     * The job runs only if this worker's claim flips it to RUNNING
     * (ForecastStore.claim), so a duplicate queue entry is a no-op. If
     * Postgres or Redis fails mid-way -- after the pop, or on the
     * attempt's own writes -- the job is left as it is (waiting, or
     * RUNNING) and ForecastRecovery finishes the story once the
     * dependency is back, instead of the job being lost.
     */
    private void process(String forecastId) {
        MDC.put(MDC_JOB_ID, forecastId);
        try {
            if (!store.claim(forecastId)) {
                log.atInfo()
                        .addKeyValue("event", "job_skipped")
                        .log("dequeued forecast is missing or not runnable; skipped");
                return;
            }
            attempt(store.find(forecastId).orElseThrow());
        } catch (DataAccessException e) {
            log.atWarn()
                    .addKeyValue("event", "job_interrupted")
                    .log("a dependency failed during the job; recovery will re-run it: {}",
                            e.getClass().getSimpleName());
            dependencyUnavailable("job", e);
        } finally {
            MDC.remove(MDC_JOB_ID);
        }
    }

    /**
     * One WARN per outage rather than one per poll (every 100 ms), and a
     * pause before the next poll, so a Redis or Postgres outage neither
     * floods the logs nor spins the scheduler thread.
     */
    private void dependencyUnavailable(String during, DataAccessException e) {
        if (!dependencyDown) {
            dependencyDown = true;
            log.atWarn()
                    .addKeyValue("event", "worker_dependency_unavailable")
                    .addKeyValue("during", during)
                    .log("worker paused: {}", e.getClass().getSimpleName());
        }
        try {
            Thread.sleep(errorBackoff.toMillis());
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    private void dependencyAvailable() {
        if (dependencyDown) {
            dependencyDown = false;
            log.atInfo()
                    .addKeyValue("event", "worker_dependency_available")
                    .log("worker resumed");
        }
    }

    private void attempt(Forecast forecast) {
        spans.continued(forecast.traceParent(), "forecast.job.attempt", () -> runAttempt(forecast));
    }

    private void runAttempt(Forecast forecast) {
        int attemptNumber = forecast.attempts() + 1;
        spans.tag("job.id", forecast.id());
        spans.tag("job.attempt", attemptNumber);
        log.atInfo()
                .addKeyValue("event", "job_started")
                .addKeyValue("attempt", attemptNumber)
                .log("forecast job started");

        long startNanos = System.nanoTime();
        ForecastOutcome outcome;
        metrics.workerBusy(true);
        try {
            // Redacted once, here, so the stored error, the 422 body, the
            // log line and the span all carry the same safe text.
            outcome = runner.run(forecast.request()).redacted(redactor);
        } finally {
            metrics.workerBusy(false);
        }
        long durationNanos = System.nanoTime() - startNanos;
        long durationMs = durationNanos / 1_000_000;
        Forecast attempted = forecast.withAttempts(attemptNumber);

        if (outcome.success()) {
            store.save(attempted.withOutcome(outcome));
            metrics.recordAttempt("succeeded", durationNanos);
            metrics.recordStageTimings(outcome.timingsMs());
            spans.tag("job.outcome", "succeeded");
            log.atInfo()
                    .addKeyValue("event", "job_succeeded")
                    .addKeyValue("attempt", attemptNumber)
                    .addKeyValue("duration_ms", durationMs)
                    .log("forecast job succeeded");
        } else if (outcome.transientFailure() && attempted.attempts() < maxAttempts) {
            store.save(attempted.withStatus(Forecast.Status.RETRYING));
            queue.enqueue(forecast.id());
            metrics.recordAttempt("retry_scheduled", durationNanos);
            metrics.recordFailure(outcome.errorCode(), false);
            recordFailedAttempt("retry_scheduled", outcome);
            log.atWarn()
                    .addKeyValue("event", "job_retry_scheduled")
                    .addKeyValue("attempt", attemptNumber)
                    .addKeyValue("max_attempts", maxAttempts)
                    .addKeyValue("duration_ms", durationMs)
                    .addKeyValue("error_code", outcome.errorCode())
                    .log("forecast job failed transiently, re-enqueued: {}", outcome.error());
        } else {
            store.save(attempted.withOutcome(outcome));
            metrics.recordAttempt("failed", durationNanos);
            metrics.recordFailure(outcome.errorCode(), true);
            recordFailedAttempt("failed", outcome);
            log.atError()
                    .addKeyValue("event", "job_failed")
                    .addKeyValue("attempt", attemptNumber)
                    .addKeyValue("duration_ms", durationMs)
                    .addKeyValue("error_code", outcome.errorCode())
                    .addKeyValue("transient", outcome.transientFailure())
                    .log("forecast job failed: {}", outcome.error());
        }
    }

    private void recordFailedAttempt(String jobOutcome, ForecastOutcome outcome) {
        spans.tag("job.outcome", jobOutcome);
        spans.tag("error.code", outcome.errorCode());
        spans.fail(outcome.errorCode() + ": " + outcome.error());
    }
}
