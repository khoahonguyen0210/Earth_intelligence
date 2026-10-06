package com.example.backend.forecast;

import java.util.Optional;

public interface ForecastQueue {

    void enqueue(String forecastId);

    Optional<String> dequeue();

    long size();

    boolean contains(String forecastId);
}
