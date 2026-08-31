package com.example.backend.storage;

import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

/**
 * Task 13.4: the only object keys ObjectStore accepts. No caller writes
 * through the store yet (docs/object-storage-contract.md), so the rule is
 * fixed before one does -- and before any key is built from request data:
 *
 *   - relative "segment/segment/name" of [A-Za-z0-9._-] segments,
 *   - no empty, "." or ".." segment, no leading or trailing "/",
 *   - at most 1,024 bytes (S3's own key limit).
 *
 * S3 itself has no directories, so ".." is not a traversal there. But a
 * key is also a path wherever objects are mirrored to a filesystem or
 * shown to a person, and nothing legitimate needs one. A key that breaks
 * the rule is a programming error, so it is refused, never repaired.
 */
public final class ObjectKeys {

    private static final Pattern SEGMENT = Pattern.compile("[A-Za-z0-9._-]+");
    private static final int MAX_KEY_BYTES = 1024;

    private ObjectKeys() {
    }

    public static String requireSafe(String key) {
        if (key == null || key.isEmpty()) {
            throw new IllegalArgumentException("object key must not be empty");
        }
        if (key.getBytes(StandardCharsets.UTF_8).length > MAX_KEY_BYTES) {
            throw new IllegalArgumentException("object key exceeds " + MAX_KEY_BYTES + " bytes");
        }
        for (String segment : key.split("/", -1)) {
            if (segment.equals(".") || segment.equals("..") || !SEGMENT.matcher(segment).matches()) {
                throw new IllegalArgumentException("object key has an unsafe segment: " + key);
            }
        }
        return key;
    }
}
