package com.example.backend.logging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Task 13.1 end to end: the real application, real logging configuration
 * (application.properties' logging.structured.format.console), a real
 * HTTP request -- asserting on the actual console bytes, not on logback
 * events. Needs the same `docker compose up -d` stack as
 * BackendApplicationTests.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ExtendWith(OutputCaptureExtension.class)
class StructuredLoggingIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void anHttpRequestProducesOneEcsJsonLineCarryingTheRequestId(CapturedOutput output) throws Exception {
        HttpResponse<String> response = HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/actuator/health"))
                        .header(RequestIdFilter.HEADER, "itest-request-42")
                        .build(),
                HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("itest-request-42", response.headers().firstValue(RequestIdFilter.HEADER).orElseThrow());

        String line = Arrays.stream(output.getOut().split("\\R"))
                .filter(candidate -> candidate.contains("\"itest-request-42\"") && candidate.contains("http_request"))
                .findFirst()
                .orElseThrow(() -> new AssertionError("no http_request line for the request id in:\n" + output));

        JsonNode json = new ObjectMapper().readTree(line);
        assertFalse(json.path("@timestamp").asString().isEmpty(), "timestamp");
        assertEquals("INFO", json.path("log").path("level").asString());
        assertEquals("backend", json.path("service").path("name").asString());
        assertEquals("itest-request-42", json.path("request_id").asString());
        assertEquals("http_request", json.path("event").asString());
        assertEquals("GET", json.path("http_method").asString());
        assertEquals("/actuator/health", json.path("http_path").asString());
        assertEquals(200, json.path("http_status").asInt());
        assertTrue(json.path("duration_ms").isNumber(), "duration_ms");
    }
}
