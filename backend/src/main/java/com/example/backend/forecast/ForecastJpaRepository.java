package com.example.backend.forecast;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ForecastJpaRepository extends JpaRepository<ForecastEntity, String> {
}
