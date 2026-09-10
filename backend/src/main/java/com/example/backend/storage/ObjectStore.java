package com.example.backend.storage;

import java.util.Optional;

/**
 * A small key/blob abstraction for large artifacts that don't belong in
 * a relational row (see docs/object-storage-contract.md) -- plots,
 * large GeoJSON payloads, model files. Four operations, each referenced
 * by key: put, get, exists, delete.
 */
public interface ObjectStore {

    void put(String key, byte[] content, String contentType);

    Optional<byte[]> get(String key);

    boolean exists(String key);

    void delete(String key);
}
