package com.example.backend.forecast;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ForecastJpaRepository extends JpaRepository<ForecastEntity, String> {

    Optional<ForecastEntity> findByIdempotencyKey(String idempotencyKey);
}
