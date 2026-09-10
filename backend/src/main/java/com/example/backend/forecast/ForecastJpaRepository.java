package com.example.backend.forecast;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ForecastJpaRepository extends JpaRepository<ForecastEntity, String> {

    Optional<ForecastEntity> findByIdempotencyKey(String idempotencyKey);

    /**
     * A worker may run a job only if this flips it to RUNNING -- one
     * conditional UPDATE, so of two workers holding the same id (a
     * duplicate queue entry, a re-enqueued orphan) exactly one wins.
     */
    @Modifying
    @Transactional
    @Query("update ForecastEntity f set f.status = 'RUNNING', f.updatedAt = :now "
            + "where f.id = :id and f.status in ('PENDING', 'RETRYING')")
    int claim(@Param("id") String id, @Param("now") Instant now);

    @Query("select f.id from ForecastEntity f where f.status = 'RUNNING' and f.updatedAt < :before "
            + "order by f.updatedAt")
    List<String> findRunningUnchangedSince(@Param("before") Instant before);

    @Query("select f.id from ForecastEntity f where f.status in ('PENDING', 'RETRYING') "
            + "and f.updatedAt < :before order by f.updatedAt")
    List<String> findWaitingUnchangedSince(@Param("before") Instant before);

    /** Ends an abandoned attempt -- only if it is still RUNNING and still unchanged, so one sweep wins. */
    @Modifying
    @Transactional
    @Query("update ForecastEntity f set f.status = :status, f.attempts = f.attempts + 1, f.error = :error, "
            + "f.updatedAt = :now where f.id = :id and f.status = 'RUNNING' and f.updatedAt < :before")
    int endAbandonedAttempt(
            @Param("id") String id,
            @Param("status") String status,
            @Param("error") String error,
            @Param("before") Instant before,
            @Param("now") Instant now);

    /** Marks a waiting job as just re-enqueued -- only if still waiting and unchanged, so one sweep wins. */
    @Modifying
    @Transactional
    @Query("update ForecastEntity f set f.updatedAt = :now where f.id = :id "
            + "and f.status in ('PENDING', 'RETRYING') and f.updatedAt < :before")
    int touchWaiting(@Param("id") String id, @Param("before") Instant before, @Param("now") Instant now);
}
