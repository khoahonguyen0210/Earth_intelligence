package com.example.backend.query;

import com.example.backend.validation.RequestShape;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * The Ask Earth page's own request -- a bare natural-language question,
 * nothing else. Every other request type this API has (AnalysisRequest,
 * ForecastRequest) already carries a resolved region/time_range/
 * operation; this is the one route where those are exactly what the
 * planner is asked to work out, not something the caller supplies.
 * Bounded the same way the API's other free-text field already is
 * (AnalysisRequest.question).
 */
public record EarthQueryRequest(@NotBlank @Size(max = RequestShape.MAX_QUESTION) String question) {
}
