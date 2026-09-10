package com.example.backend.analysis;

import com.example.backend.validation.RequestShape;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * Shape and size bounds (RequestShape). Which operations and
 * intents are supported stays the pipeline's call, with its contract's
 * FAILED/422 -- only their length is bounded here. The @JsonIgnore'd
 * checks are never part of the JSON sent to Python or stored.
 */
public record AnalysisRequest(
        @NotBlank @Size(max = RequestShape.MAX_QUESTION) String question,
        @NotBlank @Size(max = RequestShape.MAX_TOKEN) String intent,
        @Valid @NotNull RegionSpec region,
        @Valid @NotNull TimeRangeSpec timeRange,
        @NotBlank @Size(max = RequestShape.MAX_TOKEN) String operation) {

    public record RegionSpec(
            @NotBlank @Pattern(regexp = RequestShape.REGION_KINDS, message = "must be bbox, coordinates or named")
            String kind,
            @NotNull Object value) {

        @JsonIgnore
        @AssertTrue(message = "value must match kind: a name, 4 numbers (bbox) or 2 numbers (coordinates)")
        public boolean isValueShapedForKind() {
            return RequestShape.regionValueMatchesKind(kind, value);
        }
    }

    public record TimeRangeSpec(@NotBlank String start, @NotBlank String end) {

        @JsonIgnore
        @AssertTrue(message = "start and end must be ISO 8601 dates or date-times")
        public boolean isIso8601() {
            return RequestShape.isIsoDateOrDateTime(start) && RequestShape.isIsoDateOrDateTime(end);
        }
    }
}
