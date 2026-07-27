package com.example.backend.forecast;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ForecastRequest(@Valid @NotNull RegionSpec region, @NotBlank String cutoff) {

    public record RegionSpec(@NotBlank String kind, @NotNull Object value) {
    }
}
