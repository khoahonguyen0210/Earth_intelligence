package com.example.backend.forecast;

import java.util.Optional;

public interface ForecastQueue {

    void enqueue(String forecastId);

    Optional<String> dequeue();

    /** Ids currently waiting (not yet dequeued) -- the queue-depth metric. */
    long size();

    boolean contains(String forecastId);
}
