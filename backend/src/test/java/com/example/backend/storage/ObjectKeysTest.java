package com.example.backend.storage;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.backend.tracing.Spans;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.s3.S3Client;

class ObjectKeysTest {

    @Test
    void plainRelativeKeysPass() {
        assertEquals("forecasts/2024-08-15/grid.geojson", ObjectKeys.requireSafe("forecasts/2024-08-15/grid.geojson"));
        assertEquals("models/v1/model.json", ObjectKeys.requireSafe("models/v1/model.json"));
        assertEquals("a", ObjectKeys.requireSafe("a"));
    }

    @Test
    void traversalAbsoluteEmptyAndOddKeysAreRefused() {
        for (String key : new String[] {
                "", "../secret", "a/../../b", "./a", "/etc/passwd", "a/", "a//b", "a\\b", "C:\\x",
                "a b", "a\nb", "résultat", "%2e%2e/x"}) {
            assertThrows(IllegalArgumentException.class, () -> ObjectKeys.requireSafe(key), key);
        }
        assertThrows(IllegalArgumentException.class, () -> ObjectKeys.requireSafe(null));
        assertThrows(IllegalArgumentException.class, () -> ObjectKeys.requireSafe("k".repeat(1025)));
    }

    @Test
    void theStoreRefusesAnUnsafeKeyBeforeAnyS3Call() {
        S3Client neverCalled = org.mockito.Mockito.mock(S3Client.class, invocation -> {
            if (invocation.getMethod().getName().equals("headBucket")) {
                return null;
            }
            throw new AssertionError("S3 was called with an unsafe key");
        });
        S3ObjectStore store = new S3ObjectStore(neverCalled, "bucket", Spans.noop());

        assertThrows(IllegalArgumentException.class, () -> store.put("../x", new byte[0], "text/plain"));
        assertThrows(IllegalArgumentException.class, () -> store.get("/etc/passwd"));
        assertThrows(IllegalArgumentException.class, () -> store.exists("a/../b"));
        assertThrows(IllegalArgumentException.class, () -> store.delete(""));
    }
}
