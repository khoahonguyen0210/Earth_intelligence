package com.example.backend.query;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import tools.jackson.databind.ObjectMapper;

/**
 * End to end: the real application on a random port, real
 * Postgres (same `docker compose up -d` stack as BackendApplicationTests),
 * the real ServerPort event wiring (not the unit tests' setForTest) --
 * proving PythonEarthQueryRunner really learns this app's own randomly
 * bound port and passes it to the subprocess as
 * ASK_EARTH_BACKEND_BASE_URL, exactly as a real run_forecast/
 * get_result_evidence step would need. The stub script stands in for the
 * real planner/dispatch pipeline (which needs a live Gemini key); that
 * pipeline is ml/tests/query/test_run_ask_earth.py's own job.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EarthQueryIntegrationTest {

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("ask-earth.python.script-path",
                () -> Path.of("src", "test", "resources", "well_behaved_ask_earth_stub.py")
                        .toAbsolutePath().toString());
        registry.add("ask-earth.python.working-directory", () -> ".");
    }

    @LocalServerPort
    private int port;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private HttpResponse<String> send(HttpRequest.Builder request) throws Exception {
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void aQuestionIsAnsweredAndTheSubprocessLearnedTheRealBoundPort() throws Exception {
        HttpResponse<String> created = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/queries"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"question\":\"How many fires in California?\"}")));

        assertEquals(201, created.statusCode(), created.body());
        String id = objectMapper.readTree(created.body()).path("id").asString();

        HttpResponse<String> status = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/queries/" + id)));
        assertEquals(200, status.statusCode());
        assertEquals("SUCCEEDED", objectMapper.readTree(status.body()).path("status").asString());

        HttpResponse<String> result = send(
                HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/queries/" + id + "/result")));
        assertEquals(200, result.statusCode());
        var body = objectMapper.readTree(result.body()).path("result");
        assertEquals("There were 3 fires (computed).", body.path("answer").asString());

        // The real point of this test: the subprocess really learned this
        // app's own randomly bound port, via the real WebServerInitializedEvent.
        assertEquals("http://localhost:" + port, body.path("backend_base_url_seen").asString());
    }

    @Test
    void anUnknownQueryIdIs404OnEveryRoute() throws Exception {
        assertEquals(404, send(HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/queries/does-not-exist"))).statusCode());
        assertEquals(404, send(HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/queries/does-not-exist/result"))).statusCode());
    }

    @Test
    void aBlankQuestionIsRefusedWithA400() throws Exception {
        HttpResponse<String> response = send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/queries"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"question\":\"\"}")));

        assertEquals(400, response.statusCode());
        assertTrue(objectMapper.readTree(response.body()).path("error").asString().contains("question"));
    }
}
