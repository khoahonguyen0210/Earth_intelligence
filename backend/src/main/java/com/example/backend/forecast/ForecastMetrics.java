package com.example.backend.forecast;

import com.example.backend.logging.ErrorCode;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

/**
 * Task 13.2: the forecast pipeline's Micrometer meters, exported in
 * Prometheus format at /actuator/prometheus (docs/metrics.md). Names
 * below are Micrometer's dotted form; Prometheus sees them snake-cased
 * with unit suffixes (forecast.job.duration -> forecast_job_duration_seconds).
 *
 * Every tag has a small, closed value set -- outcome, error code,
 * stage -- never an id or user input, so no request can create a new
 * time series.
 */
@Component
public class ForecastMetrics {

    /** The only stage names the Python side reports (query/run_forecast.py); anything else is ignored. */
    // model_fit is reported only by the train-then-predict path (tests);
    // the product loads a trained model instead and reports model_load.
    static final Set<String> STAGES = Set.of("data_load", "model_fit", "model_load", "model_inference", "total");

    private final MeterRegistry registry;
    private final AtomicInteger busy = new AtomicInteger();

    public ForecastMetrics(MeterRegistry registry, ForecastQueue queue) {
        this.registry = registry;

        // Reads Redis LLEN on every scrape -- the same number KEDA scales
        // on. NaN (a gap in the graph) if Redis is unreachable, rather than
        // failing the whole scrape or reporting a fake 0.
        Gauge.builder("forecast.queue.depth", queue, ForecastMetrics::sizeOrNaN)
                .description("Forecast job ids waiting in the Redis queue")
                .register(registry);

        Gauge.builder("forecast.worker.busy", busy, AtomicInteger::get)
                .description("1 while this replica's worker is running a job, else 0; "
                        + "avg_over_time gives utilization")
                .register(registry);
    }

    private static double sizeOrNaN(ForecastQueue queue) {
        try {
            return queue.size();
        } catch (RuntimeException unreachable) {
            return Double.NaN;
        }
    }

    void workerBusy(boolean isBusy) {
        busy.set(isBusy ? 1 : 0);
    }

    /** One job attempt's wall-clock time, tagged succeeded / retry_scheduled / failed. */
    void recordAttempt(String outcome, long durationNanos) {
        Timer.builder("forecast.job.duration")
                .description("Wall-clock time of one forecast job attempt, including the Python subprocess")
                .tag("outcome", outcome)
                .register(registry)
                .record(durationNanos, TimeUnit.NANOSECONDS);
    }

    /**
     * One failed attempt. terminal=true means the job ended FAILED (the
     * handbook's "job failure count"); terminal=false means it was
     * retried.
     */
    void recordFailure(ErrorCode errorCode, boolean terminal) {
        Counter.builder("forecast.job.failures")
                .description("Failed forecast job attempts")
                .tag("error_code", errorCode == null ? "UNKNOWN" : errorCode.name())
                .tag("terminal", Boolean.toString(terminal))
                .register(registry)
                .increment();
    }

    /**
     * The Python pipeline's self-reported stage timings. stage=
     * "model_inference" is the handbook's "model inference time": scoring
     * the inference rows only, excluding data loading and model fitting.
     */
    void recordStageTimings(Map<String, Double> timingsMs) {
        timingsMs.forEach((stage, millis) -> {
            if (STAGES.contains(stage) && millis != null && millis >= 0) {
                Timer.builder("forecast.python.stage.duration")
                        .description("Python forecast pipeline stage wall-clock time, as reported by the pipeline")
                        .tag("stage", stage)
                        .register(registry)
                        .record(Duration.ofNanos(Math.round(millis * 1_000_000)));
            }
        });
    }
}
