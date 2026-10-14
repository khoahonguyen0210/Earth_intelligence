package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataIntegrityViolationException;

abstract class ForecastStoreContract {

    static final ForecastRequest REQUEST = new ForecastRequest(
            new ForecastRequest.RegionSpec("named", "california"), "2024-08-15T10:00:00Z");

    protected abstract ForecastStore store();

    protected abstract void backdate(String id, Duration age);

    private static String newId() {
        return UUID.randomUUID().toString();
    }

    private String saved(Forecast.Status status, Duration age) {
        String id = newId();
        store().save(Forecast.pending(id, REQUEST, Instant.now()).withStatus(status));
        backdate(id, age);
        return id;
    }

    @Test
    void aSavedForecastIsFoundById() {
        String id = newId();
        Instant created = Instant.now().truncatedTo(ChronoUnit.MILLIS);
        store().save(Forecast.pending(id, REQUEST, created, "key-" + id, "00-trace-span-01"));

        Forecast found = store().find(id).orElseThrow();

        assertEquals(id, found.id());
        assertEquals(REQUEST, found.request());
        assertEquals(Forecast.Status.PENDING, found.status());
        assertEquals(created, found.createdAt().truncatedTo(ChronoUnit.MILLIS));
        assertEquals("key-" + id, found.idempotencyKey());
        assertEquals("00-trace-span-01", found.traceParent());
        assertEquals(0, found.attempts());
        assertNull(found.result());
    }

    @Test
    void anUnknownIdIsEmpty() {
        assertTrue(store().find(newId()).isEmpty());
        assertTrue(store().findByIdempotencyKey("missing-" + newId()).isEmpty());
    }

    @Test
    void savingAgainReplacesStatusResultAndAttempts() {
        String id = newId();
        Forecast pending = Forecast.pending(id, REQUEST, Instant.now());
        store().save(pending);

        Map<String, Object> result = Map.of("peak", 0.42, "cells", List.of(Map.of("tile", "CA_1")));
        store().save(pending.withAttempts(2).withOutcome(ForecastOutcome.success(result, Map.of())));

        Forecast found = store().find(id).orElseThrow();
        assertEquals(Forecast.Status.SUCCEEDED, found.status());
        assertEquals(2, found.attempts());
        assertEquals(result, found.result());
    }

    @Test
    void aForecastIsFoundByItsIdempotencyKey() {
        String id = newId();
        String key = "key-" + id;
        store().save(Forecast.pending(id, REQUEST, Instant.now(), key));

        assertEquals(id, store().findByIdempotencyKey(key).orElseThrow().id());
    }

    @Test
    void anIdempotencyKeyCannotBelongToTwoForecasts() {
        String key = "key-" + newId();
        store().save(Forecast.pending(newId(), REQUEST, Instant.now(), key));

        assertThrows(DataIntegrityViolationException.class,
                () -> store().save(Forecast.pending(newId(), REQUEST, Instant.now(), key)));
    }

    @Test
    void theSameForecastCanBeSavedAgainWithItsKey() {
        String id = newId();
        String key = "key-" + id;
        Forecast pending = Forecast.pending(id, REQUEST, Instant.now(), key);
        store().save(pending);

        store().save(pending.withStatus(Forecast.Status.RUNNING));

        assertEquals(Forecast.Status.RUNNING, store().findByIdempotencyKey(key).orElseThrow().status());
    }

    @Test
    void aWaitingForecastIsClaimedExactlyOnce() {
        String pending = saved(Forecast.Status.PENDING, Duration.ZERO);
        String retrying = saved(Forecast.Status.RETRYING, Duration.ZERO);

        assertTrue(store().claim(pending));
        assertFalse(store().claim(pending));
        assertTrue(store().claim(retrying));
        assertEquals(Forecast.Status.RUNNING, store().find(pending).orElseThrow().status());
    }

    @Test
    void finishedAndUnknownForecastsCannotBeClaimed() {
        assertFalse(store().claim(saved(Forecast.Status.SUCCEEDED, Duration.ZERO)));
        assertFalse(store().claim(saved(Forecast.Status.FAILED, Duration.ZERO)));
        assertFalse(store().claim(newId()));
    }

    @Test
    void staleRunningForecastsAreListedOldestFirst() {
        String older = saved(Forecast.Status.RUNNING, Duration.ofMinutes(10));
        String newer = saved(Forecast.Status.RUNNING, Duration.ofMinutes(5));
        String fresh = saved(Forecast.Status.RUNNING, Duration.ZERO);
        String waiting = saved(Forecast.Status.PENDING, Duration.ofMinutes(10));

        List<String> stale = store().runningUnchangedSince(Instant.now().minusSeconds(60));

        assertTrue(stale.indexOf(older) >= 0 && stale.indexOf(older) < stale.indexOf(newer));
        assertFalse(stale.contains(fresh));
        assertFalse(stale.contains(waiting));
    }

    @Test
    void staleWaitingForecastsIncludePendingAndRetrying() {
        String pending = saved(Forecast.Status.PENDING, Duration.ofMinutes(4));
        String retrying = saved(Forecast.Status.RETRYING, Duration.ofMinutes(8));
        String fresh = saved(Forecast.Status.PENDING, Duration.ZERO);
        String running = saved(Forecast.Status.RUNNING, Duration.ofMinutes(8));

        List<String> stale = store().waitingUnchangedSince(Instant.now().minusSeconds(60));

        assertTrue(stale.indexOf(retrying) >= 0 && stale.indexOf(retrying) < stale.indexOf(pending));
        assertFalse(stale.contains(fresh));
        assertFalse(stale.contains(running));
    }

    @Test
    void anAbandonedAttemptIsEndedOnceAndCounted() {
        String id = saved(Forecast.Status.RUNNING, Duration.ofMinutes(5));
        Instant before = Instant.now().minusSeconds(60);

        assertTrue(store().endAbandonedAttempt(id, Forecast.Status.RETRYING, "worker lost", before));
        assertFalse(store().endAbandonedAttempt(id, Forecast.Status.RETRYING, "worker lost", before));

        Forecast found = store().find(id).orElseThrow();
        assertEquals(Forecast.Status.RETRYING, found.status());
        assertEquals(1, found.attempts());
        assertEquals("worker lost", found.error());
    }

    @Test
    void aRecentlyUpdatedRunningForecastIsNotAbandoned() {
        String id = saved(Forecast.Status.RUNNING, Duration.ZERO);

        assertFalse(store().endAbandonedAttempt(
                id, Forecast.Status.FAILED, "worker lost", Instant.now().minusSeconds(60)));
        assertEquals(Forecast.Status.RUNNING, store().find(id).orElseThrow().status());
    }

    @Test
    void touchingAWaitingForecastResetsItsAge() {
        String stale = saved(Forecast.Status.PENDING, Duration.ofMinutes(5));
        String running = saved(Forecast.Status.RUNNING, Duration.ofMinutes(5));
        Instant before = Instant.now().minusSeconds(60);

        assertTrue(store().touchWaiting(stale, before));
        assertFalse(store().touchWaiting(stale, before));
        assertFalse(store().touchWaiting(running, before));
        assertFalse(store().waitingUnchangedSince(before).contains(stale));
    }
}
