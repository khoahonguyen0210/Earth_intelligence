package com.example.backend.validation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.forecast.ForecastRequest;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class RequestShapeTest {

    private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void regionValuesMustMatchTheirKind() {
        assertTrue(RequestShape.regionValueMatchesKind("named", "california"));
        assertTrue(RequestShape.regionValueMatchesKind("bbox", List.of(-120.0, 37, -119.5, 37.5)));
        assertTrue(RequestShape.regionValueMatchesKind("coordinates", List.of(37.5, -120.0)));

        assertFalse(RequestShape.regionValueMatchesKind("named", ""));
        assertFalse(RequestShape.regionValueMatchesKind("named", "x".repeat(101)));
        assertFalse(RequestShape.regionValueMatchesKind("named", List.of(1, 2)));
        assertFalse(RequestShape.regionValueMatchesKind("bbox", List.of(1, 2, 3)));
        assertFalse(RequestShape.regionValueMatchesKind("bbox", List.of(1, 2, 3, "4")));
        assertFalse(RequestShape.regionValueMatchesKind("bbox", List.of(1, 2, 3, Double.NaN)));
        assertFalse(RequestShape.regionValueMatchesKind("coordinates", Map.of("lat", 1, "lon", 2)));
    }

    @Test
    void timestampsMustBeIsoDatesOrDateTimes() {
        assertTrue(RequestShape.isIsoDateOrDateTime("2024-08-15T10:00:00Z"));
        assertTrue(RequestShape.isIsoDateOrDateTime("2024-08-15T10:00:00+02:00"));
        assertTrue(RequestShape.isIsoDateOrDateTime("2024-08-15T10:00:00"));
        assertTrue(RequestShape.isIsoDateOrDateTime("2024-08-15"));

        assertFalse(RequestShape.isIsoDateOrDateTime("yesterday"));
        assertFalse(RequestShape.isIsoDateOrDateTime("2024-13-01"));
        assertFalse(RequestShape.isIsoDateOrDateTime("2024-08-15T10:00:00Z" + " ".repeat(30)));
    }

    @Test
    void aForecastRequestReportsEachBrokenFieldByName() {
        ForecastRequest request = new ForecastRequest(
                new ForecastRequest.RegionSpec("polygon", List.of(1, 2)), "not-a-date");

        List<String> paths = validator.validate(request).stream()
                .map(violation -> violation.getPropertyPath().toString())
                .sorted()
                .toList();

        assertEquals(List.of("cutoffIso8601", "region.kind"), paths);
    }

    @Test
    void theChecksNeverBecomePartOfTheJsonSentToPythonOrStored() {
        ForecastRequest request = new ForecastRequest(
                new ForecastRequest.RegionSpec("named", "california"), "2024-08-15T10:00:00Z");

        String json = new ObjectMapper().writeValueAsString(request);

        assertEquals("{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"2024-08-15T10:00:00Z\"}",
                json);
    }
}
