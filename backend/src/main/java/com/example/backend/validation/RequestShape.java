package com.example.backend.validation;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.function.Function;

/**
 * The request shapes the API contracts already lock
 * (docs/forecast-api-contract.md, RegionSpec), checked in Java
 * before a Python process or a queued job is spent on a request that can
 * only fail. Only the shape is checked here -- whether a bbox lies in
 * California, or a date range is sensible, stays the pipeline's call and
 * keeps its contract's 422.
 */
public final class RequestShape {

    public static final String REGION_KINDS = "bbox|coordinates|named";
    public static final int MAX_REGION_NAME = 100;
    public static final int MAX_QUESTION = 1_000;
    public static final int MAX_TOKEN = 64;
    public static final int MAX_TIMESTAMP = 40;

    private static final List<Function<String, ?>> ISO_FORMS =
            List.of(OffsetDateTime::parse, LocalDateTime::parse, LocalDate::parse);

    private RequestShape() {
    }

    /**
     * `value` matches `kind`: a region name, 4 numbers (west, south, east,
     * north) or 2 numbers (latitude, longitude). An unknown or missing
     * kind is reported by its own constraint, not twice here.
     */
    public static boolean regionValueMatchesKind(String kind, Object value) {
        if (kind == null) {
            return true;
        }
        return switch (kind) {
            case "named" -> value instanceof String name && !name.isBlank() && name.length() <= MAX_REGION_NAME;
            case "bbox" -> isFiniteNumbers(value, 4);
            case "coordinates" -> isFiniteNumbers(value, 2);
            default -> true;
        };
    }

    private static boolean isFiniteNumbers(Object value, int count) {
        return value instanceof List<?> items
                && items.size() == count
                && items.stream().allMatch(item -> item instanceof Number number && Double.isFinite(number.doubleValue()));
    }

    /**
     * An ISO 8601 date or date-time, the forms the pipeline's boundary
     * parser accepts (query/time_range.py). Blank is left to @NotBlank.
     */
    public static boolean isIsoDateOrDateTime(String text) {
        if (text == null || text.isBlank()) {
            return true;
        }
        if (text.length() > MAX_TIMESTAMP) {
            return false;
        }
        for (Function<String, ?> form : ISO_FORMS) {
            try {
                form.apply(text);
                return true;
            } catch (DateTimeParseException ignored) {
                // not this form; try the next
            }
        }
        return false;
    }
}
