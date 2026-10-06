package com.example.backend.forecast;

import com.example.backend.logging.SecretRedactor;
import com.example.backend.region.RegionStore;
import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

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
    private final RegionStore regionStore;
    private volatile boolean dependencyDown;

    public ForecastWorker(
            ForecastQueue queue,
            ForecastStore store,
            ForecastRunner runner,
            @Value("${forecast.worker.max-attempts}") int maxAttempts,
            SecretRedactor redactor,
            ForecastMetrics metrics,
            Spans spans,
            @Value("${forecast.worker.error-backoff-ms}") long errorBackoffMs,
            RegionStore regionStore) {
        this.queue = queue;
        this.store = store;
        this.runner = runner;
        this.maxAttempts = maxAttempts;
        this.redactor = redactor;
        this.metrics = metrics;
        this.spans = spans;
        this.errorBackoff = Duration.ofMillis(errorBackoffMs);
        this.regionStore = regionStore;
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
            outcome = runner.run(forecast.request()).redacted(redactor);
        } finally {
            metrics.workerBusy(false);
        }
        long durationNanos = System.nanoTime() - startNanos;
        long durationMs = durationNanos / 1_000_000;
        Forecast attempted = forecast.withAttempts(attemptNumber);

        if (outcome.success()) {
            store.save(attempted.withOutcome(outcome));
            if (outcome.result() instanceof Map<?, ?> resultMap) {
                regionStore.recordFrom(resultMap.get("evidence"));
            }
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
