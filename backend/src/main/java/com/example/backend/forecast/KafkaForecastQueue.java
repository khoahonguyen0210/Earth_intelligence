package com.example.backend.forecast;

import com.example.backend.tracing.Spans;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Properties;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.apache.kafka.clients.admin.Admin;
import org.apache.kafka.clients.admin.AdminClientConfig;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.admin.OffsetSpec;
import org.apache.kafka.clients.consumer.OffsetAndMetadata;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.Producer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.TopicPartition;
import org.apache.kafka.common.errors.TopicExistsException;
import org.apache.kafka.common.serialization.StringSerializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

@Component
@ConditionalOnProperty(name = "forecast.queue", havingValue = "kafka")
public class KafkaForecastQueue implements ForecastQueue, DisposableBean {

    private static final Logger log = LoggerFactory.getLogger(KafkaForecastQueue.class);

    private final Producer<String, String> producer;
    private final Admin admin;
    private final String topic;
    private final String consumerGroup;
    private final Duration timeout;
    private final ObjectMapper objectMapper;
    private final Spans spans;

    @Autowired
    public KafkaForecastQueue(
            @Value("${forecast.kafka.bootstrap-servers}") String bootstrapServers,
            @Value("${forecast.kafka.topic}") String topic,
            @Value("${forecast.kafka.consumer-group}") String consumerGroup,
            @Value("${forecast.kafka.partitions}") int partitions,
            @Value("${forecast.kafka.create-topic}") boolean createTopic,
            @Value("${forecast.kafka.timeout-ms}") long timeoutMs,
            ObjectMapper objectMapper,
            Spans spans) {
        this(new KafkaProducer<>(producerProperties(bootstrapServers, timeoutMs)),
                Admin.create(adminProperties(bootstrapServers, timeoutMs)),
                topic, consumerGroup, Duration.ofMillis(timeoutMs), objectMapper, spans);
        if (createTopic) {
            createTopicIfMissing(partitions);
        }
    }

    KafkaForecastQueue(
            Producer<String, String> producer,
            Admin admin,
            String topic,
            String consumerGroup,
            Duration timeout,
            ObjectMapper objectMapper,
            Spans spans) {
        this.producer = producer;
        this.admin = admin;
        this.topic = topic;
        this.consumerGroup = consumerGroup;
        this.timeout = timeout;
        this.objectMapper = objectMapper;
        this.spans = spans;
    }

    static Properties producerProperties(String bootstrapServers, long timeoutMs) {
        Properties properties = new Properties();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        properties.put(ProducerConfig.ACKS_CONFIG, "all");
        properties.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        properties.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, timeoutMs);
        properties.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, (int) timeoutMs);
        properties.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, (int) timeoutMs + 1000);
        properties.put(ProducerConfig.LINGER_MS_CONFIG, 0);
        return properties;
    }

    static Properties adminProperties(String bootstrapServers, long timeoutMs) {
        Properties properties = new Properties();
        properties.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        properties.put(AdminClientConfig.REQUEST_TIMEOUT_MS_CONFIG, (int) timeoutMs);
        properties.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, (int) timeoutMs);
        return properties;
    }

    @Override
    public void enqueue(String forecastId) {
        spans.child("forecast.queue.enqueue", () -> {
            spans.tag("messaging.system", "kafka");
            spans.tag("messaging.destination.name", topic);
            Map<String, Object> message = new LinkedHashMap<>();
            message.put("job_id", forecastId);
            message.put("enqueued_at", Instant.now().toString());
            String traceParent = spans.currentTraceParent();
            if (traceParent != null) {
                message.put("trace_parent", traceParent);
            }
            ProducerRecord<String, String> record =
                    new ProducerRecord<>(topic, forecastId, objectMapper.writeValueAsString(message));
            try {
                producer.send(record).get(timeout.toMillis(), TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new DataAccessResourceFailureException("interrupted while publishing to Kafka", e);
            } catch (ExecutionException | TimeoutException | KafkaException e) {
                throw new DataAccessResourceFailureException("could not publish forecast job to Kafka", e);
            }
        });
    }

    @Override
    public Optional<String> dequeue() {
        return Optional.empty();
    }

    @Override
    public boolean contains(String forecastId) {
        return false;
    }

    @Override
    public long size() {
        try {
            List<TopicPartition> partitions = admin.describeTopics(List.of(topic))
                    .allTopicNames().get(timeout.toMillis(), TimeUnit.MILLISECONDS)
                    .get(topic).partitions().stream()
                    .map(info -> new TopicPartition(topic, info.partition()))
                    .toList();
            Map<TopicPartition, OffsetAndMetadata> committed = admin.listConsumerGroupOffsets(consumerGroup)
                    .partitionsToOffsetAndMetadata().get(timeout.toMillis(), TimeUnit.MILLISECONDS);
            Map<TopicPartition, Long> latest = offsets(partitions, OffsetSpec.latest());
            Map<TopicPartition, Long> earliest = offsets(partitions, OffsetSpec.earliest());
            long lag = 0;
            for (TopicPartition partition : partitions) {
                OffsetAndMetadata done = committed.get(partition);
                long from = done == null ? earliest.get(partition) : done.offset();
                lag += Math.max(0, latest.get(partition) - from);
            }
            return lag;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return 0;
        } catch (ExecutionException | TimeoutException | KafkaException e) {
            log.atDebug().log("could not read Kafka consumer lag: {}", e.getClass().getSimpleName());
            return 0;
        }
    }

    private Map<TopicPartition, Long> offsets(List<TopicPartition> partitions, OffsetSpec spec)
            throws InterruptedException, ExecutionException, TimeoutException {
        Map<TopicPartition, OffsetSpec> request = new HashMap<>();
        partitions.forEach(partition -> request.put(partition, spec));
        Map<TopicPartition, Long> offsets = new HashMap<>();
        admin.listOffsets(request).all().get(timeout.toMillis(), TimeUnit.MILLISECONDS)
                .forEach((partition, info) -> offsets.put(partition, info.offset()));
        return offsets;
    }

    void createTopicIfMissing(int partitions) {
        try {
            admin.createTopics(List.of(new NewTopic(topic, partitions, (short) 1)))
                    .all().get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (ExecutionException e) {
            if (!(e.getCause() instanceof TopicExistsException)) {
                throw new DataAccessResourceFailureException("could not create Kafka topic " + topic, e);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new DataAccessResourceFailureException("interrupted while creating Kafka topic", e);
        } catch (TimeoutException e) {
            throw new DataAccessResourceFailureException("timed out creating Kafka topic " + topic, e);
        }
    }

    @Override
    public void destroy() {
        producer.close(timeout);
        admin.close(timeout);
    }
}
