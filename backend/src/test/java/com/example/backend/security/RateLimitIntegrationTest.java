package com.example.backend.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RateLimitIntegrationTest {

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("api.rate-limit.forecasts-per-minute", () -> "3");
        registry.add("api.rate-limit.analyses-per-minute", () -> "2");
    }

    @LocalServerPort
    private int port;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> post(String path) throws Exception {
        return http.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString("{}"))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> get(String path) throws Exception {
        return http.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void eachWorkStartingRouteHasItsOwnPerClientBudgetAndReadsHaveNone() throws Exception {
        List<Integer> forecasts = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            forecasts.add(post("/forecasts").statusCode());
        }
        assertEquals(List.of(400, 400, 400, 429), forecasts, "3 per minute, then refused");

        HttpResponse<String> refused = post("/forecasts");
        assertEquals(429, refused.statusCode());
        long retryAfter = Long.parseLong(refused.headers().firstValue("Retry-After").orElseThrow());
        assertTrue(retryAfter >= 1 && retryAfter <= 60, "Retry-After within the window: " + retryAfter);
        assertTrue(refused.body().contains("rate limit exceeded"), refused.body());

        // A separate budget per route: analyses are unaffected by the forecasts above.
        assertEquals(400, post("/analyses").statusCode());
        assertEquals(400, post("/analyses").statusCode());
        assertEquals(429, post("/analyses").statusCode());

        // Reads and probes are never limited.
        for (int i = 0; i < 10; i++) {
            assertEquals(404, get("/forecasts/does-not-exist").statusCode());
        }
        assertEquals(200, get("/readyz").statusCode());
    }
}
