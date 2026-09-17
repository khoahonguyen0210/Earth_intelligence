package com.example.backend.storage;

import java.util.Optional;

public interface ObjectStore {

    void put(String key, byte[] content, String contentType);

    Optional<byte[]> get(String key);

    boolean exists(String key);

    void delete(String key);
}
