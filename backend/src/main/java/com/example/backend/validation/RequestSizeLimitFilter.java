package com.example.backend.validation;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
public class RequestSizeLimitFilter extends OncePerRequestFilter {

    private final long maxRequestBytes;

    public RequestSizeLimitFilter(@Value("${api.max-request-bytes}") long maxRequestBytes) {
        this.maxRequestBytes = maxRequestBytes;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long length = request.getContentLengthLong();
        boolean chunked = "chunked".equalsIgnoreCase(request.getHeader("Transfer-Encoding"));

        if (length > maxRequestBytes) {
            refuse(response, 413, "request body exceeds " + maxRequestBytes + " bytes");
            return;
        }
        if (chunked) {
            refuse(response, 411, "request body must declare its Content-Length");
            return;
        }
        chain.doFilter(request, response);
    }

    private static void refuse(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.getOutputStream().write(("{\"error\":\"" + message + "\"}").getBytes(StandardCharsets.UTF_8));
    }
}
