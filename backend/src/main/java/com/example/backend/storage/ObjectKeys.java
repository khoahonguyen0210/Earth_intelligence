package com.example.backend.storage;

import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;

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
