package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.example.backend.tracing.Spans;
import java.time.Instant;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.CancellationReason;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItemsRequest;
import software.amazon.awssdk.services.dynamodb.model.TransactionCanceledException;
import tools.jackson.databind.ObjectMapper;

class DynamoDbForecastStoreTest {

    private static final ForecastRequest REQUEST = ForecastStoreContract.REQUEST;

    private final DynamoDbClient client = mock(DynamoDbClient.class);

    private DynamoDbForecastStore store() {
        return new DynamoDbForecastStore(client, new ObjectMapper(),
                new DynamoDbForecastStoreIntegrationTest.FakeObjectStore(), Spans.noop(), "jobs", false, 1024);
    }

    @Test
    @SuppressWarnings("unchecked")
    void anUnreachableTableIsReportedAsADataAccessFailure() {
        when(client.getItem(any(Consumer.class))).thenThrow(SdkClientException.create("connection refused"));
        when(client.getItem(any(GetItemRequest.class))).thenThrow(SdkClientException.create("connection refused"));

        assertThrows(DataAccessResourceFailureException.class, () -> store().find("job-1"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void aTransactionCancelledForAnotherReasonIsNotTreatedAsADuplicate() {
        TransactionCanceledException throttled = TransactionCanceledException.builder()
                .message("throttled")
                .cancellationReasons(List.of(CancellationReason.builder().code("ThrottlingError").build()))
                .build();
        when(client.transactWriteItems(any(Consumer.class))).thenThrow(throttled);
        when(client.transactWriteItems(any(TransactWriteItemsRequest.class))).thenThrow(throttled);

        Forecast forecast = Forecast.pending("job-1", REQUEST, Instant.now(), "key-1");

        assertThrows(DataAccessResourceFailureException.class, () -> store().save(forecast));
    }

    @Test
    @SuppressWarnings("unchecked")
    void aTakenIdempotencyKeyIsADataIntegrityViolation() {
        TransactionCanceledException duplicate = TransactionCanceledException.builder()
                .message("conditional check failed")
                .cancellationReasons(List.of(
                        CancellationReason.builder().code("None").build(),
                        CancellationReason.builder().code("ConditionalCheckFailed").build()))
                .build();
        when(client.transactWriteItems(any(Consumer.class))).thenThrow(duplicate);
        when(client.transactWriteItems(any(TransactWriteItemsRequest.class))).thenThrow(duplicate);

        Forecast forecast = Forecast.pending("job-1", REQUEST, Instant.now(), "key-1");

        assertThrows(DataIntegrityViolationException.class, () -> store().save(forecast));
    }
}
