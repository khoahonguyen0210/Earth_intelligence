package com.example.backend.logging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class SecretRedactorTest {

    @Test
    void masksEveryOccurrenceOfEveryConfiguredSecret() {
        SecretRedactor redactor = SecretRedactor.of("firms-key-123", "db-password-xyz");

        String redacted = redactor.redact(
                "GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/firms-key-123/VIIRS failed; "
                        + "retried with firms-key-123; db said db-password-xyz is wrong");

        assertFalse(redacted.contains("firms-key-123"));
        assertFalse(redacted.contains("db-password-xyz"));
        assertEquals(3, redacted.split("\\*\\*\\*", -1).length - 1);
    }

    @Test
    void ignoresBlankAndTooShortValuesSoOrdinaryTextIsNeverMasked() {
        SecretRedactor redactor = SecretRedactor.of("", "abc", null);

        assertEquals("abc forecast failed", redactor.redact("abc forecast failed"));
    }

    @Test
    void truncatesOversizedTextAfterRedacting() {
        SecretRedactor redactor = SecretRedactor.of("secret-value");
        String huge = "secret-value " + "x".repeat(SecretRedactor.MAX_LOGGED_LENGTH * 2);

        String redacted = redactor.redact(huge);

        assertTrue(redacted.startsWith(SecretRedactor.MASK));
        assertTrue(redacted.endsWith("...(truncated)"));
        assertEquals(SecretRedactor.MAX_LOGGED_LENGTH + "...(truncated)".length(), redacted.length());
    }

    @Test
    void nullStaysNull() {
        assertNull(SecretRedactor.of("secret-value").redact(null));
    }
}
