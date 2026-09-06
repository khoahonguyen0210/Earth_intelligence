package com.example.backend.forecast;

import java.util.Optional;

/**
 * Task 6.5: the durable hand-off between ForecastController (producer)
 * and ForecastWorker (consumer). dequeue blocks for a bounded time and
 * returns empty on timeout, matching how ForecastWorker polls it, so a
 * caller never busy-waits.
 */
public interface ForecastQueue {

    void enqueue(String forecastId);

    Optional<String> dequeue();

    /** Task 13.2: ids currently waiting (not yet dequeued) -- the queue-depth metric. */
    long size();

    /**
     * Task 13.5: whether the id is waiting in the queue now -- how
     * ForecastRecovery tells a job queued behind a backlog from one whose
     * queue entry was lost (never enqueued, or popped by a worker that
     * then failed).
     */
    boolean contains(String forecastId);
}
