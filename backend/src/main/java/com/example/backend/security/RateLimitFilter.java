package com.example.backend.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Task 13.4: per-client rate limits on the two routes that start real
 * work -- POST /forecasts queues a Python job that can run for minutes,
 * POST /analyses holds a request thread for a Python subprocess. Reads
 * are not limited.
 *
 * A fixed one-minute window per client IP and route, counted in the
 * Redis every replica already shares, so the limit holds across
 * replicas. One Lua script increments and sets the expiry atomically: a
 * separate INCR then EXPIRE could leave a key with no expiry if the
 * process died in between, locking that client out for good.
 *
 * The client is request.getRemoteAddr(). With
 * server.forward-headers-strategy=native, Tomcat replaces it with the
 * X-Forwarded-For client only when the direct peer is a private-network
 * proxy (the cloud ALB), so a client cannot pick its own identity.
 *
 * Fails open: if Redis cannot be reached, the request goes through and a
 * WARN is logged. A forecast then fails on the queue anyway, and an
 * analysis -- which does not need Redis -- keeps working.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
public class RateLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RateLimitFilter.class);
    private static final long WINDOW_SECONDS = 60;

    /** Returns {count in this window, seconds until the window resets}. */
    private static final RedisScript<List> COUNT_IN_WINDOW = RedisScript.of("""
            local count = redis.call('INCR', KEYS[1])
            if count == 1 or redis.call('TTL', KEYS[1]) < 0 then
              redis.call('EXPIRE', KEYS[1], ARGV[1])
            end
            return {count, redis.call('TTL', KEYS[1])}
            """, List.class);

    private final StringRedisTemplate redis;
    private final String keyPrefix;
    private final Map<String, Long> limitsPerMinute;

    public RateLimitFilter(
            StringRedisTemplate redis,
            @Value("${api.rate-limit.key-prefix}") String keyPrefix,
            @Value("${api.rate-limit.forecasts-per-minute}") long forecastsPerMinute,
            @Value("${api.rate-limit.analyses-per-minute}") long analysesPerMinute) {
        this.redis = redis;
        this.keyPrefix = keyPrefix;
        this.limitsPerMinute = Map.of("/forecasts", forecastsPerMinute, "/analyses", analysesPerMinute);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"POST".equals(request.getMethod()) || !limitsPerMinute.containsKey(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String route = request.getRequestURI();
        long limit = limitsPerMinute.get(route);
        String key = keyPrefix + route + ":" + request.getRemoteAddr();

        List<?> counted;
        try {
            counted = redis.execute(COUNT_IN_WINDOW, List.of(key), String.valueOf(WINDOW_SECONDS));
        } catch (DataAccessException e) {
            log.atWarn()
                    .addKeyValue("event", "rate_limit_unavailable")
                    .log("rate limit store unreachable; request allowed: {}", e.getClass().getSimpleName());
            chain.doFilter(request, response);
            return;
        }

        long count = ((Number) counted.get(0)).longValue();
        if (count <= limit) {
            chain.doFilter(request, response);
            return;
        }

        long retryAfter = Math.max(1, ((Number) counted.get(1)).longValue());
        log.atInfo()
                .addKeyValue("event", "rate_limited")
                .addKeyValue("route", route)
                .log("rate limit exceeded");
        response.setStatus(429);
        response.setHeader("Retry-After", String.valueOf(retryAfter));
        response.setContentType("application/json");
        response.getOutputStream().write(
                ("{\"error\":\"rate limit exceeded: at most " + limit + " requests per minute to " + route + "\"}")
                        .getBytes(StandardCharsets.UTF_8));
    }
}
