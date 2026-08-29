package com.example.backend.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 13.4: the public port serves the API and two status-only probes,
 * nothing operational; metrics and component details are only on the
 * internal management port. Real application, real ports, against the
 * same `docker compose up -d` stack as BackendApplicationTests.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMetrics
class OpsSurfaceIntegrationTest {

    @LocalServerPort
    private int port;

    @LocalManagementPort
    private int managementPort;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> get(int onPort, String path) throws Exception {
        return http.send(HttpRequest.newBuilder(URI.create("http://localhost:" + onPort + path)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void thePublicPortServesNoActuatorEndpoint() throws Exception {
        assertNotEquals(port, managementPort, "a separate management port");
        for (String path : new String[] {"/actuator", "/actuator/health", "/actuator/prometheus"}) {
            assertEquals(404, get(port, path).statusCode(), path);
        }
    }

    @Test
    void thePublicProbesReportStatusOnlyNeverComponentDetails() throws Exception {
        for (String path : new String[] {"/livez", "/readyz"}) {
            HttpResponse<String> probe = get(port, path);
            assertEquals(200, probe.statusCode(), path);
            JsonNode body = new ObjectMapper().readTree(probe.body());
            assertEquals("UP", body.path("status").asString(), path);
            assertFalse(body.has("components"), path + " leaked details: " + probe.body());
            assertFalse(probe.body().contains("postgres") || probe.body().contains("redis_version"), probe.body());
        }
    }

    @Test
    void theManagementPortServesFullHealthAndMetrics() throws Exception {
        JsonNode health = new ObjectMapper().readTree(get(managementPort, "/actuator/health").body());
        assertEquals("UP", health.path("status").asString());
        assertTrue(health.path("components").has("db"), health.toString());
        assertTrue(health.path("components").has("redis"), health.toString());

        HttpResponse<String> scrape = get(managementPort, "/actuator/prometheus");
        assertEquals(200, scrape.statusCode());
        assertTrue(scrape.body().contains("forecast_queue_depth "), "metrics are served internally");
    }
}
