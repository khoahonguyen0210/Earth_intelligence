package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMetrics
class PrometheusEndpointIntegrationTest {

    @LocalServerPort
    private int port;

    @LocalManagementPort
    private int managementPort;

    private HttpResponse<String> get(int onPort, String path) throws Exception {
        return HttpClient.newHttpClient().send(
                HttpRequest.newBuilder(URI.create("http://localhost:" + onPort + path)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void servesHttpQueueAndWorkerMetricsInPrometheusFormat() throws Exception {
        assertEquals(200, get(port, "/readyz").statusCode());

        HttpResponse<String> scrape = get(managementPort, "/actuator/prometheus");

        assertEquals(200, scrape.statusCode());
        assertTrue(scrape.headers().firstValue("Content-Type").orElse("").startsWith("text/plain"),
                scrape.headers().toString());
        String body = scrape.body();
        assertTrue(body.contains("http_server_requests_seconds_count{"), "HTTP request count");
        assertTrue(body.contains("http_server_requests_seconds_bucket{"), "HTTP latency histogram");
        assertTrue(body.contains("outcome=\"SUCCESS\""), "outcome tag used for HTTP error counts");
        assertTrue(body.contains("forecast_queue_depth "), "queue depth gauge");
        assertTrue(body.contains("forecast_worker_busy "), "worker utilization gauge");
    }
}
