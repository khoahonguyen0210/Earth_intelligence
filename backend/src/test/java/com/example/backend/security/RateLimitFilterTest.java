package com.example.backend.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import jakarta.servlet.FilterChain;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RateLimitFilterTest {

    private final StringRedisTemplate redis = mock(StringRedisTemplate.class);
    private final RateLimitFilter filter = new RateLimitFilter(redis, "ratelimit:", 10, 30, 20);

    private static MockHttpServletRequest request(String method, String path, String client) {
        MockHttpServletRequest request = new MockHttpServletRequest(method, path);
        request.setRemoteAddr(client);
        return request;
    }

    @Test
    @SuppressWarnings("unchecked")
    void countsPerRouteAndClientAddress() throws Exception {
        when(redis.execute(any(RedisScript.class), anyList(), any())).thenReturn(List.of(1L, 60L));
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request("POST", "/forecasts", "203.0.113.7"), new MockHttpServletResponse(), chain);

        verify(redis).execute(any(RedisScript.class), org.mockito.ArgumentMatchers.eq(
                List.of("ratelimit:/forecasts:203.0.113.7")), any());
        verify(chain).doFilter(any(), any());
    }

    @Test
    @SuppressWarnings("unchecked")
    void overTheLimitIs429WithRetryAfterAndTheRequestNeverRuns() throws Exception {
        when(redis.execute(any(RedisScript.class), anyList(), any())).thenReturn(List.of(11L, 17L));
        FilterChain chain = mock(FilterChain.class);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request("POST", "/forecasts", "203.0.113.7"), response, chain);

        assertEquals(429, response.getStatus());
        assertEquals("17", response.getHeader("Retry-After"));
        assertTrue(response.getContentAsString().contains("at most 10 requests per minute"));
        verify(chain, never()).doFilter(any(), any());
    }

    @Test
    @SuppressWarnings("unchecked")
    void failsOpenWhenRedisIsUnreachable() throws Exception {
        when(redis.execute(any(RedisScript.class), anyList(), any()))
                .thenThrow(new RedisConnectionFailureException("down"));
        FilterChain chain = mock(FilterChain.class);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request("POST", "/analyses", "203.0.113.7"), response, chain);

        assertEquals(200, response.getStatus());
        verify(chain).doFilter(any(), any());
    }

    @Test
    @SuppressWarnings("unchecked")
    void queriesHaveTheirOwnConfiguredLimit() throws Exception {
        when(redis.execute(any(RedisScript.class), anyList(), any())).thenReturn(List.of(21L, 45L));
        FilterChain chain = mock(FilterChain.class);
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request("POST", "/queries", "203.0.113.7"), response, chain);

        assertEquals(429, response.getStatus());
        assertTrue(response.getContentAsString().contains("at most 20 requests per minute to /queries"));
        verify(chain, never()).doFilter(any(), any());
    }

    @Test
    @SuppressWarnings("unchecked")
    void readsAndOtherRoutesAreNeverCounted() throws Exception {
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request("GET", "/forecasts/abc", "203.0.113.7"), new MockHttpServletResponse(), chain);
        filter.doFilter(request("GET", "/readyz", "203.0.113.7"), new MockHttpServletResponse(), chain);

        verify(redis, never()).execute(any(RedisScript.class), anyList(), any());
    }
}
