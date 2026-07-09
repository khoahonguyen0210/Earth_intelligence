package com.example.backend.analysis;

import jakarta.validation.Valid;
import java.net.URI;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AnalysisController {

    public record AnalysisSummaryResponse(String id, String status) {
    }

    public record ResultResponse(String id, Object result, Object evidence) {
    }

    public record ErrorResponse(String error) {
    }

    private final AnalysisRunner runner;
    private final AnalysisStore store;

    public AnalysisController(AnalysisRunner runner, AnalysisStore store) {
        this.runner = runner;
        this.store = store;
    }

    @PostMapping("/analyses")
    public ResponseEntity<AnalysisSummaryResponse> createAnalysis(@Valid @RequestBody AnalysisRequest request) {
        String id = UUID.randomUUID().toString();
        AnalysisOutcome outcome = runner.run(request);
        Analysis analysis = Analysis.from(id, request, Instant.now(), outcome);

        store.save(analysis);

        return ResponseEntity.created(URI.create("/analyses/" + id))
                .body(new AnalysisSummaryResponse(analysis.id(), analysis.status().name()));
    }

    @GetMapping("/analyses/{id}")
    public ResponseEntity<AnalysisSummaryResponse> getAnalysis(@PathVariable String id) {
        return store.find(id)
                .map(analysis -> ResponseEntity.ok(new AnalysisSummaryResponse(analysis.id(), analysis.status().name())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/results/{id}")
    public ResponseEntity<?> getResult(@PathVariable String id) {
        return store.find(id)
                .<ResponseEntity<?>>map(analysis -> {
                    if (analysis.status() == Analysis.Status.FAILED) {
                        return ResponseEntity.status(422).body(new ErrorResponse(analysis.error()));
                    }

                    return ResponseEntity.ok(new ResultResponse(analysis.id(), analysis.result(), analysis.evidence()));
                })
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
