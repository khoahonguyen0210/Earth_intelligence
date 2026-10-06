package com.example.backend.validation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.ObjectMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RequestValidationIntegrationTest {

    private static final String VALID_FORECAST =
            "{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"2024-08-15T10:00:00Z\"}";

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("forecast.queue.key", () -> "validation-itest-" + UUID.randomUUID());
        registry.add("forecast.python.script-path",
                () -> Path.of("src", "test", "resources", "failing_forecast_stub.py").toAbsolutePath().toString());
        registry.add("forecast.python.working-directory", () -> ".");
    }

    @LocalServerPort
    private int port;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> post(String path, String body, String idempotencyKey) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body));
        if (idempotencyKey != null) {
            request.header("Idempotency-Key", idempotencyKey);
        }
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private static String error(HttpResponse<String> response) {
        return new ObjectMapper().readTree(response.body()).path("error").asString();
    }

    @Test
    void aWellFormedForecastIsStillAccepted() throws Exception {
        assertEquals(201, post("/forecasts", VALID_FORECAST, null).statusCode());
    }

    @Test
    void aForecastWhoseShapeBreaksTheContractIsA400NamingTheField() throws Exception {
        HttpResponse<String> badKind = post("/forecasts",
                "{\"region\":{\"kind\":\"polygon\",\"value\":\"x\"},\"cutoff\":\"2024-08-15T10:00:00Z\"}", null);
        assertEquals(400, badKind.statusCode());
        assertTrue(error(badKind).startsWith("region.kind:"), badKind.body());

        HttpResponse<String> shortBbox = post("/forecasts",
                "{\"region\":{\"kind\":\"bbox\",\"value\":[1,2,3]},\"cutoff\":\"2024-08-15T10:00:00Z\"}", null);
        assertEquals(400, shortBbox.statusCode());
        assertTrue(error(shortBbox).contains("value must match kind"), shortBbox.body());

        HttpResponse<String> badCutoff = post("/forecasts",
                "{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"next tuesday\"}", null);
        assertEquals(400, badCutoff.statusCode());
        assertTrue(error(badCutoff).contains("ISO 8601"), badCutoff.body());
        assertFalse(badCutoff.body().contains("next tuesday"), "the rejected value is not echoed back");
    }

    @Test
    void unparseableJsonIsA400ThatDoesNotQuoteTheBody() throws Exception {
        HttpResponse<String> response = post("/forecasts", "{\"region\": <script>", null);

        assertEquals(400, response.statusCode());
        assertEquals("request body is not valid JSON of the expected shape", error(response));
    }

    @Test
    void anAnalysisWithAnOverlongQuestionIsRefusedBeforeAnyPythonRuns() throws Exception {
        String body = "{\"question\":\"" + "q".repeat(1_001) + "\",\"intent\":\"count\","
                + "\"region\":{\"kind\":\"named\",\"value\":\"california\"},"
                + "\"time_range\":{\"start\":\"2024-08-01\",\"end\":\"2024-08-02\"},\"operation\":\"count\"}";

        HttpResponse<String> response = post("/analyses", body, null);

        assertEquals(400, response.statusCode());
        assertTrue(error(response).startsWith("question:"), response.body());
    }

    @Test
    void anIdempotencyKeyTheDatabaseCannotHoldIsA400NotA500() throws Exception {
        HttpResponse<String> tooLong = post("/forecasts", VALID_FORECAST, "k".repeat(256));
        assertEquals(400, tooLong.statusCode(), tooLong.body());
        assertTrue(error(tooLong).startsWith("Idempotency-Key"), tooLong.body());

        assertEquals(201, post("/forecasts", VALID_FORECAST, "k-" + UUID.randomUUID()).statusCode());
    }

    @Test
    void anOversizedBodyIs413AndAnUndeclaredLengthIs411() throws Exception {
        String padded = "{\"region\":{\"kind\":\"named\",\"value\":\"california\"},\"cutoff\":\"2024-08-15T10:00:00Z\","
                + "\"padding\":\"" + "x".repeat(70_000) + "\"}";
        HttpResponse<String> oversized = post("/forecasts", padded, null);
        assertEquals(413, oversized.statusCode());
        assertTrue(error(oversized).contains("exceeds"), oversized.body());

        HttpURLConnection chunked = (HttpURLConnection) URI.create("http://localhost:" + port + "/forecasts")
                .toURL().openConnection();
        chunked.setRequestMethod("POST");
        chunked.setDoOutput(true);
        chunked.setChunkedStreamingMode(64);
        chunked.setRequestProperty("Content-Type", "application/json");
        try (OutputStream out = chunked.getOutputStream()) {
            out.write(VALID_FORECAST.getBytes(StandardCharsets.UTF_8));
        }
        assertEquals(411, chunked.getResponseCode());
    }
}
