package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.tracing.Spans;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = "forecast.recovery.interval-seconds=3600")
class ForecastRecoveryIntegrationTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"), "2024-08-15T10:00:00Z");
    private static final int MAX_ATTEMPTS = 3;

    @Autowired
    private ForecastStore store;

    @Autowired
    private StringRedisTemplate redis;

    @Autowired
    private JdbcTemplate jdbc;

    private final String queueKey = "recovery-itest-" + UUID.randomUUID();

    private RedisForecastQueue queue() {
        return new RedisForecastQueue(redis, Spans.noop(), queueKey, 1);
    }

    private ForecastRecovery recovery(RedisForecastQueue queue) {
        ForecastMetrics metrics = new ForecastMetrics(new SimpleMeterRegistry(), queue);
        return new ForecastRecovery(store, queue, metrics, MAX_ATTEMPTS, 1, 0, 0);
    }

    private String row(Forecast.Status status, int attempts) {
        String id = UUID.randomUUID().toString();
        store.save(Forecast.pending(id, REQUEST, Instant.now()).withAttempts(attempts).withStatus(status));
        jdbc.update("update forecasts set updated_at = now() - interval '30 seconds' where id = ?", id);
        return id;
    }

    private Forecast reload(String id) {
        return store.find(id).orElseThrow();
    }

    @Test
    void aJobAbandonedMidAttemptIsRetriedAndReEnqueued() {
        RedisForecastQueue queue = queue();
        String id = row(Forecast.Status.RUNNING, 0);

        recovery(queue).recoverAbandonedAttempts();

        Forecast recovered = reload(id);
        assertEquals(Forecast.Status.RETRYING, recovered.status());
        assertEquals(1, recovered.attempts(), "the lost attempt counts against the budget");
        assertTrue(queue.contains(id));
    }

    @Test
    void aJobAbandonedOnItsLastAttemptFailsInsteadOfRetryingForever() {
        RedisForecastQueue queue = queue();
        String id = row(Forecast.Status.RUNNING, MAX_ATTEMPTS - 1);

        recovery(queue).recoverAbandonedAttempts();

        Forecast failed = reload(id);
        assertEquals(Forecast.Status.FAILED, failed.status());
        assertEquals(MAX_ATTEMPTS, failed.attempts());
        assertTrue(failed.error().contains("gave up after 3 attempts"), failed.error());
        assertFalse(queue.contains(id));
    }

    @Test
    void anOrphanedJobIsReEnqueuedButAJobWaitingInTheQueueIsLeftAlone() {
        RedisForecastQueue queue = queue();
        String orphan = row(Forecast.Status.PENDING, 0);
        String waiting = row(Forecast.Status.RETRYING, 1);
        queue.enqueue(waiting);

        recovery(queue).requeueOrphans();

        assertTrue(queue.contains(orphan), "the orphan was enqueued");
        assertEquals(1, countOccurrences(queue, waiting),
                "the already-queued job must not get a duplicate entry");
    }

    @Test
    void twoSweepsNeverBothActOnOneJob() {
        RedisForecastQueue queue = queue();
        String id = row(Forecast.Status.RUNNING, 0);

        recovery(queue).recoverAbandonedAttempts();
        recovery(queue).recoverAbandonedAttempts();

        assertEquals(1, reload(id).attempts(), "recovered exactly once, not twice");
        assertEquals(1, countOccurrences(queue, id), "re-enqueued exactly once, not twice");
    }

    private long countOccurrences(RedisForecastQueue queue, String id) {
        return redis.opsForList().range(queueKey, 0, -1).stream().filter(id::equals).count();
    }

    @Test
    void onlyOneClaimOfAJobSucceeds() {
        String id = row(Forecast.Status.PENDING, 0);

        assertTrue(store.claim(id));
        assertFalse(store.claim(id), "a second worker holding the same id must not run it");
        assertEquals(Forecast.Status.RUNNING, reload(id).status());
    }
}
