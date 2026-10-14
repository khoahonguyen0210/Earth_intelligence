package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.Properties;
import java.util.UUID;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "forecast.queue=kafka",
        "forecast.recovery.interval-seconds=3600"
})
class KafkaModeIntegrationTest {

    private static final String BOOTSTRAP =
            Optional.ofNullable(System.getenv("KAFKA_BOOTSTRAP_SERVERS")).orElse("localhost:9094");
    private static final String TOPIC = "forecast-jobs-mode-itest-" + UUID.randomUUID();

    @DynamicPropertySource
    static void kafka(DynamicPropertyRegistry registry) {
        registry.add("forecast.kafka.bootstrap-servers", () -> BOOTSTRAP);
        registry.add("forecast.kafka.topic", () -> TOPIC);
        registry.add("forecast.python.script-path",
                () -> Path.of("src/test/resources/well_behaved_forecast_stub.py").toAbsolutePath().toString());
        registry.add("forecast.python.working-directory", () -> ".");
    }

    @LocalServerPort
    private int port;

    @LocalManagementPort
    private int managementPort;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    private JsonNode send(HttpRequest.Builder request) throws Exception {
        HttpResponse<String> response = http.send(request.build(), HttpResponse.BodyHandlers.ofString());
        return json.readTree(response.body());
    }

    private ConsumerRecord<String, String> firstMessage() {
        Properties properties = new Properties();
        properties.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, BOOTSTRAP);
        properties.put(ConsumerConfig.GROUP_ID_CONFIG, "mode-itest-" + UUID.randomUUID());
        properties.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "earliest");
        properties.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        properties.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(properties)) {
            consumer.subscribe(List.of(TOPIC));
            long deadline = System.currentTimeMillis() + 30_000;
            while (System.currentTimeMillis() < deadline) {
                for (ConsumerRecord<String, String> record : consumer.poll(Duration.ofMillis(500))) {
                    return record;
                }
            }
        }
        throw new AssertionError("no message reached " + TOPIC);
    }

    @Test
    void aSubmittedJobIsPublishedAndRunThroughTheInternalEndpoint() throws Exception {
        JsonNode submitted = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/forecasts"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"2024-08-15T10:00:00Z\"}")));
        String id = submitted.path("forecast_id").asString();
        assertEquals("PENDING", submitted.path("status").asString());

        ConsumerRecord<String, String> message = firstMessage();
        assertEquals(id, message.key());
        assertEquals(id, json.readTree(message.value()).path("job_id").asString());

        URI run = URI.create("http://localhost:" + managementPort + "/actuator/forecastjobs/" + id);
        JsonNode first = send(HttpRequest.newBuilder(run).POST(HttpRequest.BodyPublishers.noBody()));
        assertEquals("ran", first.path("outcome").asString());
        assertEquals("SUCCEEDED", first.path("status").asString());

        JsonNode again = send(HttpRequest.newBuilder(run).POST(HttpRequest.BodyPublishers.noBody()));
        assertEquals("skipped", again.path("outcome").asString());

        JsonNode status = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/forecasts/" + id)));
        assertEquals("SUCCEEDED", status.path("status").asString());
    }

    @Test
    void theRunEndpointIsNotOnThePublicPort() throws Exception {
        HttpResponse<String> response = http.send(HttpRequest.newBuilder(
                        URI.create("http://localhost:" + port + "/actuator/forecastjobs/" + UUID.randomUUID()))
                .POST(HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());

        assertEquals(404, response.statusCode());
    }
}
