package com.example.backend.storage;

import java.util.Optional;

/**
 * Task 6.4: a small key/blob abstraction for large artifacts that don't
 * belong in a relational row (see docs/object-storage-contract.md) --
 * plots, large GeoJSON payloads, model files. The four operations the
 * handbook asks for: put, get, exists, delete (referenced by key).
 */
public interface ObjectStore {

    void put(String key, byte[] content, String contentType);

    Optional<byte[]> get(String key);

    boolean exists(String key);

    void delete(String key);
}
