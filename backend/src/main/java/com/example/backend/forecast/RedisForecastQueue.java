package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

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

    /** LPOS, O(queue length) -- run only for jobs waiting longer than the recovery threshold. */
    @Override
    public boolean contains(String forecastId) {
        return redisTemplate.opsForList().indexOf(queueKey, forecastId) != null;
    }

    /** LLEN -- the same number KEDA's redis trigger reads to scale (infra/k8s/autoscaling.yaml). */
    @Override
    public long size() {
        Long length = redisTemplate.opsForList().size(queueKey);
        return length == null ? 0 : length;
    }
}
