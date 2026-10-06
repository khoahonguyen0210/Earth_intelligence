package com.example.backend.tracing;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.propagation.Propagator;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class Spans {

    private static final String TRACEPARENT = "traceparent";

    private final Tracer tracer;
    private final Propagator propagator;

    public Spans(Tracer tracer, Propagator propagator) {
        this.tracer = tracer;
        this.propagator = propagator;
    }

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

    public void continued(String traceParent, String name, Runnable work) {
        Span span = traceParent == null
                ? tracer.nextSpan().name(name).start()
                : propagator.extract(Map.of(TRACEPARENT, traceParent), Map::get).name(name).start();
        inScope(span, asSupplier(work));
    }

    public String currentTraceParent() {
        Span current = tracer.currentSpan();
        if (current == null) {
            return null;
        }
        Map<String, String> carrier = new HashMap<>();
        propagator.inject(current.context(), carrier, Map::put);
        return carrier.get(TRACEPARENT);
    }

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

    static final class OutcomeFailure extends RuntimeException {
        OutcomeFailure(String message) {
            super(message, null, false, false);
        }
    }
}
