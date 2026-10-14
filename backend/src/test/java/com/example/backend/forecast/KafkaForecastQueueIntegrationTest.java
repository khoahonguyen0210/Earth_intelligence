package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.UUID;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class KafkaForecastQueueIntegrationTest {

    private static final String BOOTSTRAP =
            Optional.ofNullable(System.getenv("KAFKA_BOOTSTRAP_SERVERS")).orElse("localhost:9094");

    private final String topic = "forecast-jobs-itest-" + UUID.randomUUID();
    private final String group = "forecast-workers-itest-" + UUID.randomUUID();
    private Admin admin;
    private KafkaForecastQueue queue;

    @BeforeEach
    void createTopic() {
        admin = Admin.create(KafkaForecastQueue.adminProperties(BOOTSTRAP, 10_000));
        queue = new KafkaForecastQueue(new KafkaProducer<>(KafkaForecastQueue.producerProperties(BOOTSTRAP, 10_000)),
                admin, topic, group, Duration.ofSeconds(10), new ObjectMapper(), Spans.noop());
        queue.createTopicIfMissing(2);
        queue.createTopicIfMissing(2);
    }

    @AfterEach
    void deleteTopic() throws Exception {
        admin.deleteTopics(List.of(topic)).all().get();
        queue.destroy();
    }

    private KafkaConsumer<String, String> consumer() {
        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, BOOTSTRAP);
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, group);
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        KafkaConsumer<String, String> consumer = new KafkaConsumer<>(properties);
        consumer.subscribe(List.of(topic));
        return consumer;
    }

    private static List<ConsumerRecord<String, String>> pollAll(KafkaConsumer<String, String> consumer, int count) {
        List<ConsumerRecord<String, String>> records = new ArrayList<>();
        long deadline = System.currentTimeMillis() + 30_000;
        while (records.size() < count && System.currentTimeMillis() < deadline) {
            consumer.poll(Duration.ofMillis(500)).forEach(records::add);
        }
        return records;
    }

    @Test
    void publishedJobsReachConsumersAndCountAsLagUntilCommitted() {
        List<String> ids = List.of("job-a", "job-b", "job-c");
        ids.forEach(queue::enqueue);

        assertEquals(3, queue.size());

        try (KafkaConsumer<String, String> consumer = consumer()) {
            List<ConsumerRecord<String, String>> records = pollAll(consumer, 3);
            assertEquals(ids.stream().sorted().toList(), records.stream().map(ConsumerRecord::key).sorted().toList());
            ConsumerRecord<String, String> first = records.getFirst();
            assertEquals(first.key(), new ObjectMapper().readValue(first.value(), Map.class).get("job_id"));

            consumer.commitSync(Map.of(new TopicPartition(first.topic(), first.partition()),
                    new OffsetAndMetadata(first.offset() + 1)));
        }

        assertEquals(2, queue.size());
    }
}
