package com.example.backend.tracing;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

/**
 * The one place the backend opens its own spans, over Micrometer
 * Tracing's vendor-neutral API (the OpenTelemetry bridge and
 * OTLP exporter sit behind it, see docs/tracing.md).
 *
 * Three kinds of span, so a trace only ever starts where real work
 * starts:
 *
 *   child      -- store/queue/Python calls. Recorded only inside a trace
 *                 that is already running; outside one they run
 *                 untraced, so a stray call never becomes a one-span
 *                 orphan trace.
 *   root       -- a unit of work with nothing above it (a workflow run):
 *                 a child if something is being traced, else a new trace.
 *   continued  -- a forecast job attempt: a child of the span that
 *                 submitted the job, whose W3C traceparent was stored on
 *                 the forecast row, because the worker picks the job up
 *                 later on another thread (or another replica) where
 *                 nothing of the HTTP request's context survives.
 *
 * Every span is put in scope while its work runs, so nested spans become
 * its children and every log line written meanwhile carries its traceId
 * and spanId (MDC), the same way request_id/job_id do.
 */
@Component
public class Spans {

    private static final String TRACEPARENT = "traceparent";

    private final Tracer tracer;
    private final Propagator propagator;

    public Spans(Tracer tracer, Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

    /** Traces nothing -- for code constructed outside Spring that does not care. */
    public static Spans noop() {
        return new Spans(Tracer.NOOP, Propagator.NOOP);
    }

    public <T> T child(String name, Supplier<T> work) {
        Span parent = tracer.currentSpan();
        if (parent == null) {
            return work.get();
        }
        return inScope(tracer.nextSpan(parent).name(name).start(), work);
    }

    public void child(String name, Runnable work) {
        child(name, asSupplier(work));
    }

    public <T> T root(String name, Supplier<T> work) {
        return inScope(tracer.nextSpan().name(name).start(), work);
    }

    /** A new trace when `traceParent` is null or unreadable, e.g. a row written before tracing existed. */
    public void continued(String traceParent, String name, Runnable work) {
        Span span = traceParent == null
                ? tracer.nextSpan().name(name).start()
                : propagator.extract(Map.of(TRACEPARENT, traceParent), Map::get).name(name).start();
        inScope(span, asSupplier(work));
    }

    /** The current span's W3C traceparent, or null when nothing is being traced. */
    public String currentTraceParent() {
        Span current = tracer.currentSpan();
        if (current == null) {
            return null;
        }
        Map<String, String> carrier = new HashMap<>();
        propagator.inject(current.context(), carrier, Map::put);
        return carrier.get(TRACEPARENT);
    }

    /** Tags the current span, keeping numbers and booleans typed; a no-op when nothing is being traced. */
    public void tag(String key, Object value) {
        Span current = tracer.currentSpan();
        if (current == null || value == null) {
            return;
        }
        switch (value) {
            case Integer number -> current.tag(key, number.longValue());
            case Long number -> current.tag(key, number.longValue());
            case Double number -> current.tag(key, number.doubleValue());
            case Boolean flag -> current.tag(key, flag.booleanValue());
            default -> current.tag(key, String.valueOf(value));
        }
    }

    /**
     * Marks the current span failed for a failure that is an outcome, not
     * a thrown exception (a Python exit code, a failed workflow node). The
     * message must already be redacted -- a trace backend is as readable
     * as the logs are.
     */
    public void fail(String message) {
        Span current = tracer.currentSpan();
        if (current != null) {
            current.error(new OutcomeFailure(message));
        }
    }

    private <T> T inScope(Span span, Supplier<T> work) {
        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            return work.get();
        } catch (RuntimeException | Error e) {
            span.error(e);
            throw e;
        } finally {
            span.end();
        }
    }

    private static Supplier<Void> asSupplier(Runnable work) {
        return () -> {
            work.run();
            return null;
        };
    }

    /**
     * Carries a failure message to the span's error status. No stack
     * trace: it would only show where Spans.fail was called, not where
     * anything went wrong.
     */
    static final class OutcomeFailure extends RuntimeException {
        OutcomeFailure(String message) {
            super(message, null, false, false);
        }
    }
}
