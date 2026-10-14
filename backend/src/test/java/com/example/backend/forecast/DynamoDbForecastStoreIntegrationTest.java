package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.backend.storage.ObjectStore;
import com.example.backend.tracing.Spans;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import tools.jackson.databind.ObjectMapper;

class DynamoDbForecastStoreIntegrationTest extends ForecastStoreContract {

    private static final String TABLE = "forecast-jobs-itest-" + UUID.randomUUID();
    private static final int INLINE_LIMIT = 512;

    private static DynamoDbClient client;
    private static final FakeObjectStore objects = new FakeObjectStore();
    private static DynamoDbForecastStore store;

    static DynamoDbClient localClient() {
        String endpoint = Optional.ofNullable(System.getenv("DYNAMODB_ENDPOINT")).orElse("http://localhost:8000");
        return DynamoDbClient.builder()
                .endpointOverride(URI.create(endpoint))
                .region(Region.US_WEST_2)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create("local", "local")))
                .build();
    }

    @BeforeAll
    static void createTable() {
        client = localClient();
        store = new DynamoDbForecastStore(client, new ObjectMapper(), objects, Spans.noop(), TABLE, true, INLINE_LIMIT);
    }

    @AfterAll
    static void dropTable() {
        client.deleteTable(request -> request.tableName(TABLE));
        client.close();
    }

    @Override
    protected ForecastStore store() {
        return store;
    }

    @Override
    protected void backdate(String id, Duration age) {
        client.updateItem(request -> request
                .tableName(TABLE)
                .key(Map.of("pk", AttributeValue.fromS(DynamoDbForecastStore.JOB_PREFIX + id)))
                .updateExpression("SET updated_at = :at")
                .expressionAttributeValues(Map.of(
                        ":at", AttributeValue.fromN(Long.toString(Instant.now().minus(age).toEpochMilli())))));
    }

    private static Map<String, Object> resultOfSize(int cells) {
        return Map.of("cells", java.util.stream.IntStream.range(0, cells)
                .mapToObj(i -> Map.of("tile_id", "CA_" + i, "probability", 0.01))
                .toList());
    }

    @Test
    void creatingTheTableTwiceIsHarmless() {
        store.createTableIfMissing();
    }

    @Test
    void aSmallResultIsStoredInTheItem() {
        String id = UUID.randomUUID().toString();
        Map<String, Object> result = resultOfSize(2);
        store.save(Forecast.from(id, REQUEST, Instant.now(), ForecastOutcome.success(result)));

        assertEquals(result, store.find(id).orElseThrow().result());
        assertFalse(objects.contents.containsKey("forecasts/" + id + "/result.json"));
    }

    @Test
    void aLargeResultIsMovedToTheObjectStore() {
        String id = UUID.randomUUID().toString();
        Map<String, Object> result = resultOfSize(200);
        store.save(Forecast.from(id, REQUEST, Instant.now(), ForecastOutcome.success(result)));

        Map<String, AttributeValue> item = client.getItem(request -> request
                .tableName(TABLE)
                .key(Map.of("pk", AttributeValue.fromS(DynamoDbForecastStore.JOB_PREFIX + id)))).item();

        assertEquals("forecasts/" + id + "/result.json", item.get("result_key").s());
        assertFalse(item.containsKey("result"));
        assertTrue(objects.contents.containsKey("forecasts/" + id + "/result.json"));
        assertEquals(result, store.find(id).orElseThrow().result());
    }

    @Test
    void aMissingOffloadedResultIsReportedAsADataAccessFailure() {
        String id = UUID.randomUUID().toString();
        store.save(Forecast.from(id, REQUEST, Instant.now(), ForecastOutcome.success(resultOfSize(200))));
        objects.delete("forecasts/" + id + "/result.json");

        assertThrows(DataAccessResourceFailureException.class, () -> store.find(id));
    }

    @Test
    void recoveryQueriesFollowTheStatusIndex() {
        String id = UUID.randomUUID().toString();
        store.save(Forecast.pending(id, REQUEST, Instant.now()));
        backdate(id, Duration.ofMinutes(3));

        assertTrue(store.waitingUnchangedSince(Instant.now().minusSeconds(60)).contains(id));
        assertTrue(store.claim(id));
        assertFalse(store.waitingUnchangedSince(Instant.now().minusSeconds(60)).contains(id));
        assertEquals(List.of(), store.runningUnchangedSince(Instant.now().minusSeconds(60)).stream()
                .filter(id::equals).toList());
    }

    static final class FakeObjectStore implements ObjectStore {

        final Map<String, byte[]> contents = new ConcurrentHashMap<>();

        @Override
        public void put(String key, byte[] content, String contentType) {
            contents.put(key, content);
        }

        @Override
        public Optional<byte[]> get(String key) {
            return Optional.ofNullable(contents.get(key));
        }

        @Override
        public boolean exists(String key) {
            return contents.containsKey(key);
        }

        @Override
        public void delete(String key) {
            contents.remove(key);
        }
    }
}
