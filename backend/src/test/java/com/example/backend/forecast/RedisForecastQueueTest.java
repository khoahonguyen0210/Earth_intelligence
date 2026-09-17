package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.tracing.Spans;
import com.example.backend.tracing.TestTracing;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.sdk.trace.data.SpanData;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

class RedisForecastQueueTest {

    private static ForecastQueue newQueue(String queueKey) {
        return newQueue(queueKey, Spans.noop());
    }

    private static ForecastQueue newQueue(String queueKey, Spans spans) {
        LettuceConnectionFactory connectionFactory = new LettuceConnectionFactory(
                new RedisStandaloneConfiguration("127.0.0.1", 6379));
        connectionFactory.afterPropertiesSet();

        StringRedisTemplate redisTemplate = new StringRedisTemplate(connectionFactory);
        redisTemplate.afterPropertiesSet();

        return new RedisForecastQueue(redisTemplate, spans, queueKey, 1);
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

    @Test
    void enqueueIsAChildSpanOfTheSubmittingSpanAndDequeueIsNotTraced() {
        TestTracing tracing = new TestTracing();
        String queueKey = "test-forecast-queue-" + UUID.randomUUID();
        ForecastQueue queue = newQueue(queueKey, tracing.spans());

        tracing.spans().root("forecast.job.submit", () -> {
            queue.enqueue("job-1");
            return null;
        });
        assertEquals("job-1", queue.dequeue().orElseThrow());

        SpanData submit = tracing.only("forecast.job.submit");
        SpanData enqueue = tracing.only("forecast.queue.enqueue");
        assertEquals(submit.getSpanId(), enqueue.getParentSpanId());
        assertEquals("redis", enqueue.getAttributes().get(AttributeKey.stringKey("db.system")));
        assertEquals(queueKey, enqueue.getAttributes().get(AttributeKey.stringKey("queue.key")));
        assertEquals(2, tracing.finished().size(), "a poll is not a span: " + tracing.finished());
    }
}
