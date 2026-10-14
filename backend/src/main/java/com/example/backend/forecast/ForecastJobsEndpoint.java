package com.example.backend.forecast;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "forecastjobs")
@ConditionalOnProperty(name = "forecast.queue", havingValue = "kafka")
public class ForecastJobsEndpoint {

    private static final Pattern JOB_ID = Pattern.compile("[0-9a-fA-F-]{1,64}");

    private final ForecastWorker worker;

    public ForecastJobsEndpoint(ForecastWorker worker) {
        this.worker = worker;
    }

    @WriteOperation
    public WebEndpointResponse<Map<String, Object>> run(@Selector String id) {
        if (!JOB_ID.matcher(id).matches()) {
            return new WebEndpointResponse<>(Map.of("error", "invalid job id"), WebEndpointResponse.STATUS_BAD_REQUEST);
        }
        try {
            ForecastWorker.JobRun run = worker.runNow(id);
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("job_id", run.jobId());
            body.put("outcome", run.ran() ? "ran" : "skipped");
            body.put("status", run.status() == null ? null : run.status().name());
            body.put("attempts", run.attempts());
            return new WebEndpointResponse<>(body, WebEndpointResponse.STATUS_OK);
        } catch (DataAccessException e) {
            return new WebEndpointResponse<>(
                    Map.of("error", "a dependency is unavailable"), WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE);
        }
    }
}
