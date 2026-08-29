package com.example.backend.tracing;

import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.otel.bridge.OtelCurrentTraceContext;
import io.micrometer.tracing.otel.bridge.OtelPropagator;
import io.micrometer.tracing.otel.bridge.OtelTracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.sdk.testing.exporter.InMemorySpanExporter;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.data.SpanData;
import io.opentelemetry.sdk.trace.export.SimpleSpanProcessor;
import java.util.List;

/**
 * The same OpenTelemetry bridge the application runs (Micrometer Tracing
 * over the OTel SDK, W3C propagation), exporting synchronously into
 * memory instead of over OTLP, so unit tests assert on the real finished
 * spans -- names, parents, trace ids, attributes and status.
 */
public final class TestTracing {

    private final InMemorySpanExporter exporter = InMemorySpanExporter.create();
    private final OtelTracer tracer;
    private final Spans spans;

    public TestTracing() {
        SdkTracerProvider provider = SdkTracerProvider.builder()
                .addSpanProcessor(SimpleSpanProcessor.create(exporter))
                .build();
        io.opentelemetry.api.trace.Tracer otelTracer = provider.get("test");
        ContextPropagators propagators = ContextPropagators.create(W3CTraceContextPropagator.getInstance());

        tracer = new OtelTracer(otelTracer, new OtelCurrentTraceContext(), event -> {
        });
        spans = new Spans(tracer, new OtelPropagator(propagators, otelTracer));
    }

    public Spans spans() {
        return spans;
    }

    public Tracer tracer() {
        return tracer;
    }

    public List<SpanData> finished() {
        return exporter.getFinishedSpanItems();
    }

    public List<SpanData> named(String name) {
        return finished().stream().filter(span -> span.getName().equals(name)).toList();
    }

    public SpanData only(String name) {
        List<SpanData> matching = named(name);
        if (matching.size() != 1) {
            throw new AssertionError("expected exactly one '" + name + "' span, got " + matching.size()
                    + " among " + finished().stream().map(SpanData::getName).toList());
        }
        return matching.getFirst();
    }
}
