package com.example.backend.forecast;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.dao.DataAccessResourceFailureException;

class ForecastJobsEndpointTest {

    private static final String ID = "05cf52b9-bb49-46a8-948f-4a1e51a3fa0c";

    private final ForecastWorker worker = mock(ForecastWorker.class);
    private final ForecastJobsEndpoint endpoint = new ForecastJobsEndpoint(worker);

    @Test
    void aRunJobReportsItsFinalStatus() {
        when(worker.runNow(ID)).thenReturn(new ForecastWorker.JobRun(ID, true, Forecast.Status.SUCCEEDED, 1));

        WebEndpointResponse<Map<String, Object>> response = endpoint.run(ID);

        assertEquals(200, response.getStatus());
        assertEquals(Map.of("job_id", ID, "outcome", "ran", "status", "SUCCEEDED", "attempts", 1), response.getBody());
    }

    @Test
    void aJobThatWasNotRunnableIsReportedAsSkipped() {
        when(worker.runNow(ID)).thenReturn(new ForecastWorker.JobRun(ID, false, Forecast.Status.SUCCEEDED, 1));

        assertEquals("skipped", endpoint.run(ID).getBody().get("outcome"));
    }

    @Test
    void anUnavailableDependencyIsAServiceUnavailableResponse() {
        when(worker.runNow(ID)).thenThrow(new DataAccessResourceFailureException("db down"));

        assertEquals(503, endpoint.run(ID).getStatus());
    }

    @Test
    void aMalformedIdIsRejectedWithoutRunningAnything() {
        assertEquals(400, endpoint.run("../../etc/passwd").getStatus());
        verify(worker, never()).runNow("../../etc/passwd");
    }
}
