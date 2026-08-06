package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * Runs against the real local Redis (`docker compose up -d` in
 * infra/docker/, same as BackendApplicationTests needs real Postgres and
 * S3ObjectStoreTest needs real MinIO) -- proving the actual list-based
 * queue wiring works, not just the wrapping logic.
 */
class RedisForecastQueueTest {

    private static ForecastQueue newQueue(String queueKey) {
        LettuceConnectionFactory connectionFactory = new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("127.0.0.1", 6379));
        connectionFactory.afterPropertiesSet();

        StringRedisTemplate redisTemplate = new StringRedisTemplate(connectionFactory);
        redisTemplate.afterPropertiesSet();

        return new RedisForecastQueue(redisTemplate, queueKey, 1);
    }

    @Test
    void dequeueReturnsAnIdEnqueuedEarlier() {
        ForecastQueue queue = newQueue("test-forecast-queue-" + UUID.randomUUID());
        String forecastId = UUID.randomUUID().toString();

        queue.enqueue(forecastId);

        assertEquals(forecastId, queue.dequeue().orElseThrow());
    }

    @Test
    void dequeueReturnsIdsInFifoOrder() {
        ForecastQueue queue = newQueue("test-forecast-queue-" + UUID.randomUUID());

        queue.enqueue("first");
        queue.enqueue("second");

        assertEquals("first", queue.dequeue().orElseThrow());
        assertEquals("second", queue.dequeue().orElseThrow());
    }

    @Test
    void dequeueTimesOutOnAnEmptyQueue() {
        ForecastQueue queue = newQueue("test-forecast-queue-" + UUID.randomUUID());

        long start = System.nanoTime();
        boolean present = queue.dequeue().isPresent();
        Duration elapsed = Duration.ofNanos(System.nanoTime() - start);

        assertFalse(present);
        assertTrue(elapsed.toMillis() >= 900, "expected the blocking pop to wait roughly the poll timeout");
    }
}
