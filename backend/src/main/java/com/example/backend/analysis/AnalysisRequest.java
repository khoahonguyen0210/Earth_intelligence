package com.example.backend.analysis;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AnalysisRequest(
        @NotBlank String question,
        @NotBlank String intent,
        @Valid @NotNull RegionSpec region,
        @Valid @NotNull TimeRangeSpec timeRange,
        @NotBlank String operation) {

    public record RegionSpec(@NotBlank String kind, @NotNull Object value) {
    }

    public record TimeRangeSpec(@NotBlank String start, @NotBlank String end) {
    }
}
