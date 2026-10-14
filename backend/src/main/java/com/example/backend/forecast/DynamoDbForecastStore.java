package com.example.backend.forecast;

import com.example.backend.storage.ObjectStore;
import com.example.backend.tracing.Spans;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeDefinition;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.BillingMode;
import software.amazon.awssdk.services.dynamodb.model.CancellationReason;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.CreateTableRequest;
import software.amazon.awssdk.services.dynamodb.model.GlobalSecondaryIndex;
import software.amazon.awssdk.services.dynamodb.model.KeySchemaElement;
import software.amazon.awssdk.services.dynamodb.model.KeyType;
import software.amazon.awssdk.services.dynamodb.model.Projection;
import software.amazon.awssdk.services.dynamodb.model.ProjectionType;
import software.amazon.awssdk.services.dynamodb.model.Put;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.ResourceInUseException;
import software.amazon.awssdk.services.dynamodb.model.ScalarAttributeType;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItem;
import software.amazon.awssdk.services.dynamodb.model.TransactionCanceledException;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import tools.jackson.databind.ObjectMapper;

@Repository
@ConditionalOnProperty(name = "forecast.store", havingValue = "dynamodb")
public class DynamoDbForecastStore implements ForecastStore {

    public static final String STATUS_INDEX = "status-updated_at";
    static final String JOB_PREFIX = "JOB#";
    static final String IDEMPOTENCY_PREFIX = "IDEMPOTENCY#";
    static final String RESULT_KEY_PREFIX = "forecasts/";

    private static final Map<String, String> NAMES = Map.of(
            "#status", "status", "#error", "error", "#updated", "updated_at", "#attempts", "attempts");

    private final DynamoDbClient client;
    private final String table;
    private final ObjectMapper objectMapper;
    private final ObjectStore objectStore;
    private final Spans spans;
    private final int inlineResultMaxBytes;

    public DynamoDbForecastStore(
            DynamoDbClient client,
            ObjectMapper objectMapper,
            ObjectStore objectStore,
            Spans spans,
            @Value("${dynamodb.forecast-table}") String table,
            @Value("${dynamodb.create-table}") boolean createTable,
            @Value("${dynamodb.inline-result-max-bytes}") int inlineResultMaxBytes) {
        this.client = client;
        this.table = table;
        this.objectMapper = objectMapper;
        this.objectStore = objectStore;
        this.spans = spans;
        this.inlineResultMaxBytes = inlineResultMaxBytes;
        if (createTable) {
            createTableIfMissing();
        }
    }

    @Override
    public void save(Forecast forecast) {
        traced("forecast.store.save", () -> {
            spans.tag("forecast.status", forecast.status());
            Map<String, AttributeValue> item = toItem(forecast);
            if (forecast.idempotencyKey() == null) {
                client.putItem(request -> request.tableName(table).item(item));
                return null;
            }
            Put job = Put.builder().tableName(table).item(item).build();
            Put claimKey = Put.builder()
                    .tableName(table)
                    .item(Map.of(
                            "pk", s(IDEMPOTENCY_PREFIX + forecast.idempotencyKey()),
                            "job_id", s(forecast.id())))
                    .conditionExpression("attribute_not_exists(pk) OR job_id = :id")
                    .expressionAttributeValues(Map.of(":id", s(forecast.id())))
                    .build();
            try {
                client.transactWriteItems(request -> request.transactItems(
                        TransactWriteItem.builder().put(job).build(),
                        TransactWriteItem.builder().put(claimKey).build()));
            } catch (TransactionCanceledException e) {
                if (e.cancellationReasons().stream()
                        .map(CancellationReason::code)
                        .anyMatch("ConditionalCheckFailed"::equals)) {
                    throw new DataIntegrityViolationException("duplicate idempotency_key", e);
                }
                throw e;
            }
            return null;
        });
    }

    @Override
    public Optional<Forecast> find(String id) {
        return traced("forecast.store.find", () -> getJob(id));
    }

    @Override
    public boolean claim(String id) {
        return traced("forecast.store.claim", () -> conditionalUpdate(id,
                "SET #status = :running, #updated = :now",
                "attribute_exists(pk) AND #status IN (:pending, :retrying)",
                Map.of(":running", s("RUNNING"), ":pending", s("PENDING"), ":retrying", s("RETRYING"),
                        ":now", n(Instant.now()))));
    }

    @Override
    public List<String> runningUnchangedSince(Instant before) {
        return traced("forecast.store.running_unchanged_since", () -> idsUnchangedSince(List.of("RUNNING"), before));
    }

    @Override
    public List<String> waitingUnchangedSince(Instant before) {
        return traced("forecast.store.waiting_unchanged_since",
                () -> idsUnchangedSince(List.of("PENDING", "RETRYING"), before));
    }

    @Override
    public boolean endAbandonedAttempt(String id, Forecast.Status status, String error, Instant before) {
        Map<String, AttributeValue> values = new HashMap<>(Map.of(
                ":status", s(status.name()), ":running", s("RUNNING"), ":one", AttributeValue.fromN("1"),
                ":before", n(before), ":now", n(Instant.now())));
        String update = "SET #status = :status, #attempts = #attempts + :one, #updated = :now";
        if (error == null) {
            update += " REMOVE #error";
        } else {
            update += ", #error = :error";
            values.put(":error", s(error));
        }
        String expression = update;
        return traced("forecast.store.end_abandoned_attempt", () -> conditionalUpdate(id, expression,
                "#status = :running AND #updated < :before", values));
    }

    @Override
    public boolean touchWaiting(String id, Instant before) {
        return traced("forecast.store.touch_waiting", () -> conditionalUpdate(id,
                "SET #updated = :now",
                "#status IN (:pending, :retrying) AND #updated < :before",
                Map.of(":pending", s("PENDING"), ":retrying", s("RETRYING"), ":before", n(before),
                        ":now", n(Instant.now()))));
    }

    @Override
    public Optional<Forecast> findByIdempotencyKey(String idempotencyKey) {
        return traced("forecast.store.find_by_idempotency_key", () -> {
            Map<String, AttributeValue> claim = client.getItem(request -> request
                    .tableName(table)
                    .key(Map.of("pk", s(IDEMPOTENCY_PREFIX + idempotencyKey)))
                    .consistentRead(true)).item();
            if (claim == null || !claim.containsKey("job_id")) {
                return Optional.empty();
            }
            return getJob(claim.get("job_id").s());
        });
    }

    void createTableIfMissing() {
        try {
            client.createTable(CreateTableRequest.builder()
                    .tableName(table)
                    .billingMode(BillingMode.PAY_PER_REQUEST)
                    .attributeDefinitions(
                            attribute("pk", ScalarAttributeType.S),
                            attribute("status", ScalarAttributeType.S),
                            attribute("updated_at", ScalarAttributeType.N))
                    .keySchema(key("pk", KeyType.HASH))
                    .globalSecondaryIndexes(GlobalSecondaryIndex.builder()
                            .indexName(STATUS_INDEX)
                            .keySchema(key("status", KeyType.HASH), key("updated_at", KeyType.RANGE))
                            .projection(Projection.builder().projectionType(ProjectionType.KEYS_ONLY).build())
                            .build())
                    .build());
        } catch (ResourceInUseException alreadyThere) {
            return;
        }
        client.waiter().waitUntilTableExists(request -> request.tableName(table));
    }

    private Optional<Forecast> getJob(String id) {
        Map<String, AttributeValue> item = client.getItem(request -> request
                .tableName(table)
                .key(jobKey(id))
                .consistentRead(true)).item();
        return item == null || item.isEmpty() ? Optional.empty() : Optional.of(toDomain(item));
    }

    private boolean conditionalUpdate(
            String id, String update, String condition, Map<String, AttributeValue> values) {
        try {
            client.updateItem(UpdateItemRequest.builder()
                    .tableName(table)
                    .key(jobKey(id))
                    .updateExpression(update)
                    .conditionExpression(condition)
                    .expressionAttributeNames(namesUsedIn(update + " " + condition))
                    .expressionAttributeValues(values)
                    .build());
            return true;
        } catch (ConditionalCheckFailedException notApplicable) {
            return false;
        }
    }

    private List<String> idsUnchangedSince(List<String> statuses, Instant before) {
        record Waiting(String id, long updatedAt) {
        }
        List<Waiting> found = new ArrayList<>();
        for (String status : statuses) {
            QueryRequest query = QueryRequest.builder()
                    .tableName(table)
                    .indexName(STATUS_INDEX)
                    .keyConditionExpression("#status = :status AND #updated < :before")
                    .expressionAttributeNames(Map.of("#status", "status", "#updated", "updated_at"))
                    .expressionAttributeValues(Map.of(":status", s(status), ":before", n(before)))
                    .build();
            client.queryPaginator(query).items().forEach(item -> found.add(new Waiting(
                    item.get("pk").s().substring(JOB_PREFIX.length()),
                    Long.parseLong(item.get("updated_at").n()))));
        }
        found.sort(Comparator.comparingLong(Waiting::updatedAt));
        return found.stream().map(Waiting::id).toList();
    }

    private Map<String, AttributeValue> toItem(Forecast forecast) {
        Map<String, AttributeValue> item = new HashMap<>();
        item.put("pk", s(JOB_PREFIX + forecast.id()));
        item.put("id", s(forecast.id()));
        item.put("request", s(objectMapper.writeValueAsString(forecast.request())));
        item.put("status", s(forecast.status().name()));
        item.put("created_at", s(forecast.createdAt().toString()));
        item.put("attempts", AttributeValue.fromN(Integer.toString(forecast.attempts())));
        item.put("updated_at", n(Instant.now()));
        putIfPresent(item, "error", forecast.error());
        putIfPresent(item, "idempotency_key", forecast.idempotencyKey());
        putIfPresent(item, "trace_parent", forecast.traceParent());
        if (forecast.result() != null) {
            byte[] result = objectMapper.writeValueAsBytes(forecast.result());
            if (result.length <= inlineResultMaxBytes) {
                item.put("result", s(new String(result, StandardCharsets.UTF_8)));
            } else {
                String key = RESULT_KEY_PREFIX + forecast.id() + "/result.json";
                objectStore.put(key, result, "application/json");
                item.put("result_key", s(key));
            }
        }
        return item;
    }

    private Forecast toDomain(Map<String, AttributeValue> item) {
        return new Forecast(
                item.get("id").s(),
                objectMapper.readValue(item.get("request").s(), ForecastRequest.class),
                Instant.parse(item.get("created_at").s()),
                Forecast.Status.valueOf(item.get("status").s()),
                readResult(item),
                text(item, "error"),
                Integer.parseInt(item.get("attempts").n()),
                text(item, "idempotency_key"),
                text(item, "trace_parent"));
    }

    private Object readResult(Map<String, AttributeValue> item) {
        if (item.containsKey("result")) {
            return objectMapper.readValue(item.get("result").s(), Object.class);
        }
        if (item.containsKey("result_key")) {
            String key = item.get("result_key").s();
            byte[] stored = objectStore.get(key).orElseThrow(() -> new DataAccessResourceFailureException(
                    "forecast result " + key + " is missing from the object store"));
            return objectMapper.readValue(stored, Object.class);
        }
        return null;
    }

    private <T> T traced(String name, Supplier<T> work) {
        return spans.child(name, () -> {
            spans.tag("db.system", "dynamodb");
            spans.tag("db.name", table);
            try {
                return work.get();
            } catch (SdkException e) {
                throw new DataAccessResourceFailureException("DynamoDB request failed: " + e.getMessage(), e);
            }
        });
    }

    private static Map<String, String> namesUsedIn(String expression) {
        Map<String, String> used = new HashMap<>();
        NAMES.forEach((placeholder, name) -> {
            if (expression.contains(placeholder)) {
                used.put(placeholder, name);
            }
        });
        return used;
    }

    private static Map<String, AttributeValue> jobKey(String id) {
        return Map.of("pk", s(JOB_PREFIX + id));
    }

    private static void putIfPresent(Map<String, AttributeValue> item, String name, String value) {
        if (value != null) {
            item.put(name, s(value));
        }
    }

    private static String text(Map<String, AttributeValue> item, String name) {
        AttributeValue value = item.get(name);
        return value == null ? null : value.s();
    }

    private static AttributeValue s(String value) {
        return AttributeValue.fromS(value);
    }

    private static AttributeValue n(Instant instant) {
        return AttributeValue.fromN(Long.toString(instant.toEpochMilli()));
    }

    private static AttributeDefinition attribute(String name, ScalarAttributeType type) {
        return AttributeDefinition.builder().attributeName(name).attributeType(type).build();
    }

    private static KeySchemaElement key(String name, KeyType type) {
        return KeySchemaElement.builder().attributeName(name).keyType(type).build();
    }
}
