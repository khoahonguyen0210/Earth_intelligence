package com.example.backend.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.slf4j.event.Level;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Gives every HTTP request a request ID and one structured
 * `http_request` log line.
 *
 * The ID is put in the MDC as `request_id`, so every log line written
 * while handling the request (controller, store, Python runner) carries
 * it, and it is echoed back as the X-Request-Id response header, so a
 * client-reported problem maps straight to its log lines. A caller may
 * supply its own X-Request-Id (e.g. a load balancer), but only if it is
 * short and plain -- anything else is replaced, so a client can never
 * choose what gets written into the logs under that field.
 *
 * Runs first (HIGHEST_PRECEDENCE) so the ID exists before any other
 * filter can log, and the recorded duration covers the whole request.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-Id";
    public static final String MDC_KEY = "request_id";

    private static final Pattern ACCEPTABLE_ID = Pattern.compile("[A-Za-z0-9._-]{1,64}");
    private static final Logger log = LoggerFactory.getLogger(RequestIdFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String requestId = acceptOrGenerate(request.getHeader(HEADER));
        long startNanos = System.nanoTime();

        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);
        try {
            chain.doFilter(request, response);
        } finally {
            int status = response.getStatus();
            log.atLevel(status >= 500 ? Level.ERROR : Level.INFO)
                    .addKeyValue("event", "http_request")
                    .addKeyValue("http_method", request.getMethod())
                    .addKeyValue("http_path", request.getRequestURI())
                    .addKeyValue("http_status", status)
                    .addKeyValue("duration_ms", (System.nanoTime() - startNanos) / 1_000_000)
                    .log("{} {} -> {}", request.getMethod(), request.getRequestURI(), status);
            MDC.remove(MDC_KEY);
        }
    }

    static String acceptOrGenerate(String supplied) {
        if (supplied != null && ACCEPTABLE_ID.matcher(supplied).matches()) {
            return supplied;
        }
        return UUID.randomUUID().toString();
    }
}
