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

/**
 * Finds forecast jobs that no worker will ever finish and puts them
 * back on track -- the recovery path the queue itself does not have
 * (docs/reliability-tests.md). Postgres is the source of truth; the Redis
 * list is only a hint of what to run next.
 *
 * Two cases, both judged by how long a row has gone without changing
 * (forecasts.updated_at, V5):
 *
 *   abandoned attempt  RUNNING for longer than an attempt can take (the
 *                      Python timeout plus a grace period): the worker
 *                      died, or its final database write failed. That
 *                      counts as a failed attempt (WORKER_LOST, transient):
 *                      RETRYING and re-enqueued while attempts remain,
 *                      else FAILED -- the same budget as any retry.
 *   orphaned job       PENDING/RETRYING for longer than the threshold AND
 *                      not in the Redis list: its queue entry was never
 *                      written (Redis down at submit) or was popped by a
 *                      worker that then could not run it. Re-enqueued.
 *                      A job merely waiting behind a backlog is still in
 *                      the list and is left alone.
 *
 * Runs on every replica. Every change is a conditional UPDATE that only
 * succeeds if the row is still in the state and age the sweep saw, so two
 * replicas never both act on one job, and a job a worker claims meanwhile
 * is left to that worker. A duplicate queue entry is harmless: a worker
 * only runs a job it can claim (ForecastStore.claim).
 *
 * A sweep that cannot reach Postgres or Redis logs one WARN and tries
 * again next interval -- recovery must not itself fail loudly during the
 * very outages it exists for.
 */
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
            return; // another replica's sweep, or a late worker write, got there first
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
            queue.enqueue(forecast.id()); // if Redis is down, requeueOrphans picks it up later
        }
    }

    void requeueOrphans() {
        Instant before = Instant.now().minus(orphanedAfter);
        for (String id : store.waitingUnchangedSince(before)) {
            if (queue.contains(id) || !store.touchWaiting(id, before)) {
                continue; // queued behind a backlog, or another sweep/worker got there first
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
