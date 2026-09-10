package com.example.backend.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Response headers for an API that only ever returns JSON.
 *
 *   X-Content-Type-Options: nosniff  -- a browser never reinterprets a
 *       JSON body (which can carry request-derived text, e.g. a region
 *       label) as HTML or script.
 *   Cache-Control: no-store          -- job status and results change
 *       and are fetched by id; no shared cache keeps a copy.
 *   Strict-Transport-Security        -- only on a request that arrived
 *       over HTTPS (behind the ALB, via X-Forwarded-Proto and
 *       server.forward-headers-strategy), so a browser that has once
 *       used the HTTPS domain never falls back to plain HTTP. Never sent
 *       over plain HTTP, where the spec says to ignore it anyway.
 *
 * Set before the request is handled, so every response carries them --
 * including 4xx refusals from the filters after this one.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class SecurityHeadersFilter extends OncePerRequestFilter {

    static final String HSTS = "max-age=31536000; includeSubDomains";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setHeader("Cache-Control", "no-store");
        if (request.isSecure()) {
            response.setHeader("Strict-Transport-Security", HSTS);
        }
        chain.doFilter(request, response);
    }
}
