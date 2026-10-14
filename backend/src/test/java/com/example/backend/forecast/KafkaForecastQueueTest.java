package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.util.Map;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.producer.MockProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;
import tools.jackson.databind.ObjectMapper;

class KafkaForecastQueueTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private KafkaForecastQueue queue(MockProducer<String, String> producer) {
        return new KafkaForecastQueue(producer, mock(Admin.class), "forecast-jobs", "forecast-workers",
                Duration.ofSeconds(1), objectMapper, Spans.noop());
    }

    @Test
    void enqueuePublishesTheJobKeyedByItsId() {
        MockProducer<String, String> producer = new MockProducer<>(true, null, new StringSerializer(), new StringSerializer());

        queue(producer).enqueue("job-1");

        ProducerRecord<String, String> sent = producer.history().getFirst();
        assertEquals("forecast-jobs", sent.topic());
        assertEquals("job-1", sent.key());
        Map<?, ?> message = objectMapper.readValue(sent.value(), Map.class);
        assertEquals("job-1", message.get("job_id"));
        assertTrue(message.containsKey("enqueued_at"));
    }

    @Test
    void aFailedPublishIsADataAccessFailure() {
        MockProducer<String, String> producer = new MockProducer<>(false, null, new StringSerializer(), new StringSerializer());
        KafkaForecastQueue queue = queue(producer);

        Thread failer = Thread.ofVirtual().start(() -> {
            while (producer.history().isEmpty()) {
                Thread.onSpinWait();
            }
            producer.errorNext(new RuntimeException("broker down"));
        });

        assertThrows(DataAccessResourceFailureException.class, () -> queue.enqueue("job-1"));
        failer.interrupt();
    }

    @Test
    void anUnacknowledgedPublishTimesOut() {
        MockProducer<String, String> producer = new MockProducer<>(false, null, new StringSerializer(), new StringSerializer());

        assertThrows(DataAccessResourceFailureException.class, () -> queue(producer).enqueue("job-1"));
    }

    @Test
    void theBackendNeverConsumesFromKafka() {
        KafkaForecastQueue queue = queue(new MockProducer<>(true, null, new StringSerializer(), new StringSerializer()));

        assertTrue(queue.dequeue().isEmpty());
        assertFalse(queue.contains("job-1"));
    }
}
