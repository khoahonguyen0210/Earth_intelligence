package com.example.backend.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * Task 13.4: every public response carries the security headers --
 * successes and refusals alike -- and HSTS is sent exactly when the
 * request reached the load balancer over HTTPS. The test client is on
 * 127.0.0.1, one of Tomcat's trusted internal proxies, so its
 * X-Forwarded-Proto header stands in for the cloud ALB's.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SecurityHeadersIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> send(HttpRequest.Builder request) throws Exception {
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpRequest.Builder to(String path) {
        return HttpRequest.newBuilder(URI.create("http://localhost:" + port + path));
    }

    @Test
    void successesAndRefusalsBothCarryTheHeaders() throws Exception {
        HttpResponse<String> probe = send(to("/readyz"));
        HttpResponse<String> refused = send(to("/forecasts")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{}")));

        assertEquals(200, probe.statusCode());
        assertEquals(400, refused.statusCode());
        for (HttpResponse<String> response : java.util.List.of(probe, refused)) {
            assertEquals("nosniff", response.headers().firstValue("X-Content-Type-Options").orElse(null));
            assertEquals("no-store", response.headers().firstValue("Cache-Control").orElse(null));
        }
    }

    @Test
    void hstsOnlyWhenTheRequestArrivedOverHttps() throws Exception {
        HttpResponse<String> plain = send(to("/readyz"));
        HttpResponse<String> viaHttpsProxy = send(to("/readyz").header("X-Forwarded-Proto", "https"));

        assertTrue(plain.headers().firstValue("Strict-Transport-Security").isEmpty(), "never over plain HTTP");
        assertEquals(SecurityHeadersFilter.HSTS,
                viaHttpsProxy.headers().firstValue("Strict-Transport-Security").orElse(null));
    }
}
