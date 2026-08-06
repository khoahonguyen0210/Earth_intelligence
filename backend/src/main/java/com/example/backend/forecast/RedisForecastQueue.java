package com.example.backend.forecast;

import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/**
 * Task 6.5: a Redis list used as a simple FIFO queue -- enqueue pushes
 * onto the left end, dequeue blocks popping from the right end
 * (RPOP with a timeout), so jobs come out in the order they went in.
 * Redelivery/visibility-timeout semantics for a worker that dies mid-job
 * are Task 6.6's retry/timeout work, not this one.
 */
@Component
public class RedisForecastQueue implements ForecastQueue {

    private final StringRedisTemplate redisTemplate;
    private final String queueKey;
    private final Duration pollTimeout;

    public RedisForecastQueue(
            StringRedisTemplate redisTemplate,
            @Value("${forecast.queue.key}") String queueKey,
            @Value("${forecast.queue.poll-timeout-seconds}") long pollTimeoutSeconds) {
        this.redisTemplate = redisTemplate;
        this.queueKey = queueKey;
        this.pollTimeout = Duration.ofSeconds(pollTimeoutSeconds);
    }

    @Override
    public void enqueue(String forecastId) {
        redisTemplate.opsForList().leftPush(queueKey, forecastId);
    }

    @Override
    public Optional<String> dequeue() {
        return Optional.ofNullable(redisTemplate.opsForList().rightPop(queueKey, pollTimeout));
    }
}
