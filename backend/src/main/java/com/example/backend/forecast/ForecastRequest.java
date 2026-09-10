package com.example.backend.forecast;

import com.example.backend.validation.RequestShape;
import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * The shape docs/forecast-api-contract.md locks is enforced here
 * (RequestShape), so a malformed request is a 400 instead of a
 * queued job that can only fail. The @JsonIgnore'd checks are never part
 * of the JSON sent to Python or stored with the forecast.
 */
public record ForecastRequest(@Valid @NotNull RegionSpec region, @NotBlank String cutoff) {

    @JsonIgnore
    @AssertTrue(message = "cutoff must be an ISO 8601 date-time")
    public boolean isCutoffIso8601() {
        return RequestShape.isIsoDateOrDateTime(cutoff);
    }

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
}
