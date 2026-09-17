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

    void recordFailure(ErrorCode errorCode, boolean terminal) {
        Counter.builder("forecast.job.failures")
                .description("Failed forecast job attempts")
                .tag("error_code", errorCode == null ? "UNKNOWN" : errorCode.name())
                .tag("terminal", Boolean.toString(terminal))
                .register(registry)
                .increment();
    }

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
