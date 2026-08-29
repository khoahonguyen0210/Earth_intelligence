package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
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
 *
 * Task 13.3: enqueue is a child span. dequeue is not traced: an idle
 * worker's blocking poll would otherwise produce an empty trace every
 * poll timeout, and the job's own trace starts from the traceparent on
 * its forecast row, not from the queue (docs/tracing.md).
 */
@Component
public class RedisForecastQueue implements ForecastQueue {

    private final StringRedisTemplate redisTemplate;
    private final String queueKey;
    private final Duration pollTimeout;
    private final Spans spans;

    public RedisForecastQueue(
            StringRedisTemplate redisTemplate,
            Spans spans,
            @Value("${forecast.queue.key}") String queueKey,
            @Value("${forecast.queue.poll-timeout-seconds}") long pollTimeoutSeconds) {
        this.redisTemplate = redisTemplate;
        this.queueKey = queueKey;
        this.pollTimeout = Duration.ofSeconds(pollTimeoutSeconds);
        this.spans = spans;
    }

    @Override
    public void enqueue(String forecastId) {
        spans.child("forecast.queue.enqueue", () -> {
            spans.tag("db.system", "redis");
            spans.tag("queue.key", queueKey);
            redisTemplate.opsForList().leftPush(queueKey, forecastId);
        });
    }

    @Override
    public Optional<String> dequeue() {
        return Optional.ofNullable(redisTemplate.opsForList().rightPop(queueKey, pollTimeout));
    }

    /** LLEN -- the same number KEDA's redis trigger reads to scale (infra/k8s/autoscaling.yaml). */
    @Override
    public long size() {
        Long length = redisTemplate.opsForList().size(queueKey);
        return length == null ? 0 : length;
    }
}
