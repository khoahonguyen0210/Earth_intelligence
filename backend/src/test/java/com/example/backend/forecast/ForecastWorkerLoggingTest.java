package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.example.backend.logging.ErrorCode;
import com.example.backend.logging.SecretRedactor;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import tools.jackson.databind.ObjectMapper;

/** Task 13.1: the worker's job lifecycle events, as real logback events. */
class ForecastWorkerLoggingTest {

    private static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"),
            "2024-08-15T10:00:00Z");
    private static final String SECRET = "firms-map-key-0123456789";

    private final ListAppender<ILoggingEvent> appender = new ListAppender<>();
    private final Logger logger = (Logger) LoggerFactory.getLogger(ForecastWorker.class);

    private final Deque<String> queued = new ArrayDeque<>();
    private final ForecastQueue queue = new ForecastQueue() {
        @Override
        public void enqueue(String forecastId) {
            queued.add(forecastId);
        }

        @Override
        public Optional<String> dequeue() {
            return Optional.ofNullable(queued.poll());
        }

        @Override
        public long size() {
            return queued.size();
        }
    };
    private ForecastStore store;
    private final ForecastMetrics metrics = new ForecastMetrics(new SimpleMeterRegistry(), queue);

    @BeforeEach
    void setUp() {
        appender.start();
        logger.addAppender(appender);

        ForecastJpaRepository repository = mock(ForecastJpaRepository.class);
        Map<String, ForecastEntity> backing = new HashMap<>();
        when(repository.save(any())).thenAnswer(invocation -> {
            ForecastEntity entity = invocation.getArgument(0);
            backing.put(entity.getId(), entity);
            return entity;
        });
        when(repository.findById(any())).thenAnswer(
                invocation -> Optional.ofNullable(backing.get(invocation.getArgument(0))));
        store = new ForecastStore(repository, new ObjectMapper());
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
    }

    private ForecastWorker workerReturning(ForecastOutcome outcome, int maxAttempts) {
        store.save(Forecast.pending("job-1", REQUEST, Instant.now(), null));
        queue.enqueue("job-1");
        return new ForecastWorker(queue, store, request -> outcome, maxAttempts, SecretRedactor.of(SECRET), metrics);
    }

    private List<String> events() {
        return appender.list.stream().map(event -> (String) keyValues(event).get("event")).toList();
    }

    private ILoggingEvent last() {
        return appender.list.get(appender.list.size() - 1);
    }

    private static Map<String, Object> keyValues(ILoggingEvent event) {
        return event.getKeyValuePairs().stream()
                .filter(pair -> pair.value != null)
                .collect(Collectors.toMap(pair -> pair.key, pair -> pair.value));
    }

    @Test
    void successfulJobLogsStartedThenSucceededAllCarryingTheJobId() {
        workerReturning(ForecastOutcome.success(Map.of("model_version", "v1")), 3).pollOnce();

        assertEquals(List.of("job_started", "job_succeeded"), events());
        appender.list.forEach(event -> assertEquals("job-1", event.getMDCPropertyMap().get(ForecastWorker.MDC_JOB_ID)));
        Map<String, Object> fields = keyValues(last());
        assertEquals(1, fields.get("attempt"));
        assertTrue(((Long) fields.get("duration_ms")) >= 0);
        assertNull(MDC.get(ForecastWorker.MDC_JOB_ID), "job_id must not leak past the job");
    }

    @Test
    void permanentFailureLogsErrorCodeAndRedactsSecretsFromTheErrorText() {
        workerReturning(ForecastOutcome.failure(ErrorCode.PYTHON_FAILED,
                "requests.HTTPError for https://firms.modaps.eosdis.nasa.gov/api/area/csv/" + SECRET + "/x"), 3)
                .pollOnce();

        assertEquals(List.of("job_started", "job_failed"), events());
        ILoggingEvent failed = last();
        assertEquals("ERROR", failed.getLevel().toString());
        assertEquals(ErrorCode.PYTHON_FAILED, keyValues(failed).get("error_code"));
        assertFalse(failed.getFormattedMessage().contains(SECRET), failed.getFormattedMessage());
        assertTrue(failed.getFormattedMessage().contains("***"));
    }

    @Test
    void transientFailureWithAttemptsLeftLogsARetryWarningNotAFailure() {
        workerReturning(ForecastOutcome.transientFailure(ErrorCode.PYTHON_TIMEOUT, "timed out"), 3).pollOnce();

        assertEquals(List.of("job_started", "job_retry_scheduled"), events());
        Map<String, Object> fields = keyValues(last());
        assertEquals("WARN", last().getLevel().toString());
        assertEquals(ErrorCode.PYTHON_TIMEOUT, fields.get("error_code"));
        assertEquals(3, fields.get("max_attempts"));
    }

    @Test
    void unknownIdIsLoggedAsSkipped() {
        queue.enqueue("does-not-exist");
        new ForecastWorker(queue, store, request -> {
            throw new AssertionError("runner must not run");
        }, 3, SecretRedactor.of(), metrics).pollOnce();

        assertEquals(List.of("job_skipped"), events());
        assertEquals("does-not-exist", last().getMDCPropertyMap().get(ForecastWorker.MDC_JOB_ID));
    }
}
