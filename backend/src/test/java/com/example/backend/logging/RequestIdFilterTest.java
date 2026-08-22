package com.example.backend.logging;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RequestIdFilterTest {

    private final RequestIdFilter filter = new RequestIdFilter();
    private final ListAppender<ILoggingEvent> appender = new ListAppender<>();
    private final Logger logger = (Logger) LoggerFactory.getLogger(RequestIdFilter.class);

    @BeforeEach
    void attachAppender() {
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void detachAppender() {
        logger.detachAppender(appender);
    }

    @Test
    void generatesAnIdPutsItInTheMdcDuringTheRequestAndEchoesIt() throws Exception {
        AtomicReference<String> idSeenByHandler = new AtomicReference<>();
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(new MockHttpServletRequest("GET", "/forecasts/abc"), response,
                (req, res) -> idSeenByHandler.set(MDC.get(RequestIdFilter.MDC_KEY)));

        String echoed = response.getHeader(RequestIdFilter.HEADER);
        assertTrue(echoed.matches("[0-9a-f-]{36}"), echoed);
        assertEquals(echoed, idSeenByHandler.get());
        assertNull(MDC.get(RequestIdFilter.MDC_KEY), "MDC must not leak into the next request on this thread");
    }

    @Test
    void keepsAPlainCallerSuppliedId() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/actuator/health");
        request.addHeader(RequestIdFilter.HEADER, "lb-7f3a.19_x");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, (req, res) -> { });

        assertEquals("lb-7f3a.19_x", response.getHeader(RequestIdFilter.HEADER));
    }

    @Test
    void replacesACallerSuppliedIdThatCouldForgeLogContent() {
        assertNotEquals("a\nevent=fake", RequestIdFilter.acceptOrGenerate("a\nevent=fake"));
        assertNotEquals("x".repeat(65), RequestIdFilter.acceptOrGenerate("x".repeat(65)));
        assertNotEquals("", RequestIdFilter.acceptOrGenerate(""));
    }

    @Test
    void logsOneHttpRequestEventWithMethodPathStatusAndDuration() throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(new MockHttpServletRequest("POST", "/forecasts"), response,
                (req, res) -> ((MockHttpServletResponse) res).setStatus(201));

        assertEquals(1, appender.list.size());
        ILoggingEvent event = appender.list.get(0);
        Map<String, Object> fields = keyValues(event);
        assertEquals("http_request", fields.get("event"));
        assertEquals("POST", fields.get("http_method"));
        assertEquals("/forecasts", fields.get("http_path"));
        assertEquals(201, fields.get("http_status"));
        assertTrue(((Long) fields.get("duration_ms")) >= 0);
        assertEquals(response.getHeader(RequestIdFilter.HEADER),
                event.getMDCPropertyMap().get(RequestIdFilter.MDC_KEY));
    }

    @Test
    void serverErrorsAreLoggedAtErrorLevel() throws Exception {
        filter.doFilter(new MockHttpServletRequest("GET", "/results/x"), new MockHttpServletResponse(),
                (req, res) -> ((MockHttpServletResponse) res).setStatus(500));

        assertEquals("ERROR", appender.list.get(0).getLevel().toString());
    }

    static Map<String, Object> keyValues(ILoggingEvent event) {
        return event.getKeyValuePairs().stream().collect(Collectors.toMap(pair -> pair.key, pair -> pair.value));
    }
}
