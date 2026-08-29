package com.example.backend.storage;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.tracing.Spans;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

/**
 * Runs against the real local MinIO (`docker compose up -d` in
 * infra/docker/, same as BackendApplicationTests needs real Postgres) --
 * proving the actual network/serialization wiring works, not just the
 * wrapping logic.
 */
class S3ObjectStoreTest {

    private static ObjectStore newStore() {
        S3Client client = S3Client.builder()
                .endpointOverride(URI.create("http://localhost:9000"))
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("ai_earth", "ai_earth_dev")))
                .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                .build();

        return new S3ObjectStore(client, "ai-earth-artifacts-test", Spans.noop());
    }

    @Test
    void putThenGetReturnsTheSameBytes() {
        ObjectStore store = newStore();
        String key = "test/" + UUID.randomUUID() + ".txt";
        byte[] content = "hello object storage".getBytes(StandardCharsets.UTF_8);

        store.put(key, content, "text/plain");
        Optional<byte[]> result = store.get(key);

        assertTrue(result.isPresent());
        assertArrayEquals(content, result.get());
    }

    @Test
    void getReturnsEmptyForMissingKey() {
        ObjectStore store = newStore();

        assertTrue(store.get("test/does-not-exist-" + UUID.randomUUID()).isEmpty());
    }

    @Test
    void existsReflectsWhetherTheKeyIsPresent() {
        ObjectStore store = newStore();
        String key = "test/" + UUID.randomUUID() + ".txt";

        assertFalse(store.exists(key));

        store.put(key, "x".getBytes(StandardCharsets.UTF_8), "text/plain");

        assertTrue(store.exists(key));
    }

    @Test
    void deleteRemovesTheObject() {
        ObjectStore store = newStore();
        String key = "test/" + UUID.randomUUID() + ".txt";
        store.put(key, "x".getBytes(StandardCharsets.UTF_8), "text/plain");

        assertTrue(store.exists(key));

        store.delete(key);

        assertFalse(store.exists(key));
    }
}
