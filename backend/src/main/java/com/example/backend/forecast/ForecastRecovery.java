package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import java.time.Duration;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ForecastRecovery {

    private static final Logger log = LoggerFactory.getLogger(ForecastRecovery.class);

    private final ForecastStore store;
    private final ForecastQueue queue;
    private final ForecastMetrics metrics;
    private final int maxAttempts;
    private final Duration abandonedAfter;
    private final Duration orphanedAfter;

    public ForecastRecovery(
            ForecastStore store,
            ForecastQueue queue,
            ForecastMetrics metrics,
            @Value("${forecast.worker.max-attempts}") int maxAttempts,
            @Value("${forecast.python.timeout-seconds}") long pythonTimeoutSeconds,
            @Value("${forecast.recovery.running-grace-seconds}") long runningGraceSeconds,
            @Value("${forecast.recovery.queued-after-seconds}") long queuedAfterSeconds) {
        this.store = store;
        this.queue = queue;
        this.metrics = metrics;
        this.maxAttempts = maxAttempts;
        this.abandonedAfter = Duration.ofSeconds(pythonTimeoutSeconds + runningGraceSeconds);
        this.orphanedAfter = Duration.ofSeconds(queuedAfterSeconds);
    }

    @Scheduled(
            fixedDelayString = "${forecast.recovery.interval-seconds}",
            initialDelayString = "${forecast.recovery.interval-seconds}",
            timeUnit = java.util.concurrent.TimeUnit.SECONDS)
    public void sweep() {
        try {
            recoverAbandonedAttempts();
            requeueOrphans();
        } catch (DataAccessException e) {
            log.atWarn()
                    .addKeyValue("event", "recovery_sweep_failed")
                    .log("recovery sweep could not reach a dependency; next sweep retries: {}",
                            e.getClass().getSimpleName());
        }
    }

    void recoverAbandonedAttempts() {
        Instant before = Instant.now().minus(abandonedAfter);
        for (String id : store.runningUnchangedSince(before)) {
            store.find(id).ifPresent(forecast -> endAbandonedAttempt(forecast, before));
        }
    }

    private void endAbandonedAttempt(Forecast forecast, Instant before) {
        int attempt = forecast.attempts() + 1;
        boolean retry = attempt < maxAttempts;
        String error = "the worker running attempt " + attempt + " stopped before finishing it"
                + (retry ? "" : "; gave up after " + maxAttempts + " attempts");

        if (!store.endAbandonedAttempt(forecast.id(),
                retry ? Forecast.Status.RETRYING : Forecast.Status.FAILED, error, before)) {
            return;
        }
        metrics.recordFailure(ErrorCode.WORKER_LOST, !retry);
        MDC.put(ForecastWorker.MDC_JOB_ID, forecast.id());
        try {
            log.atWarn()
                    .addKeyValue("event", "job_recovered")
                    .addKeyValue("attempt", attempt)
                    .addKeyValue("error_code", ErrorCode.WORKER_LOST)
                    .addKeyValue("outcome", retry ? "retry_scheduled" : "failed")
                    .log("abandoned attempt ended: {}", error);
        } finally {
            MDC.remove(ForecastWorker.MDC_JOB_ID);
        }
        if (retry) {
            queue.enqueue(forecast.id());
        }
    }

    void requeueOrphans() {
        Instant before = Instant.now().minus(orphanedAfter);
        for (String id : store.waitingUnchangedSince(before)) {
            if (queue.contains(id) || !store.touchWaiting(id, before)) {
                continue;
            }
            queue.enqueue(id);
            MDC.put(ForecastWorker.MDC_JOB_ID, id);
            try {
                log.atWarn()
                        .addKeyValue("event", "job_requeued")
                        .log("waiting job had no queue entry; re-enqueued");
            } finally {
                MDC.remove(ForecastWorker.MDC_JOB_ID);
            }
        }
    }
}
