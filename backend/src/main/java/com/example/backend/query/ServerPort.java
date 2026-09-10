package com.example.backend.query;

import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.boot.web.server.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

/**
 * The backend's own real, bound HTTP port -- needed because
 * PythonAskEarthRunner's subprocess calls back into this same running
 * backend (POST /forecasts, for a plan's run_forecast/get_result_evidence
 * steps; see docs/ask-earth.md). `@Value("${server.port}")` is wrong for
 * this: it is 0 in a `@SpringBootTest(webEnvironment = RANDOM_PORT)`
 * context, and the real port is only known once the server has actually
 * bound one -- exactly what WebServerInitializedEvent reports. Read at
 * request time (PythonAskEarthRunner.run), not at construction time,
 * since construction happens before this event has necessarily fired.
 *
 * The app has its own separate management.server.port, which means Boot
 * starts *two* embedded web servers -- the main one and the
 * management one -- each firing its own WebServerInitializedEvent. A
 * real run against the full app caught this: without filtering, whichever
 * of the two fired last silently won, occasionally handing out the
 * management port instead of the real one.
 * WebServerApplicationContext.getServerNamespace() is exactly Boot's own
 * way to tell them apart: null/"" for the main server, "management" for
 * the other -- only the former is ever routed to /forecasts and friends.
 */
@Component
public class ServerPort implements ApplicationListener<WebServerInitializedEvent> {

    private volatile int port = -1;

    @Override
    public void onApplicationEvent(WebServerInitializedEvent event) {
        if (WebServerApplicationContext.hasServerNamespace(event.getApplicationContext(), "management")) {
            return;
        }
        port = event.getWebServer().getPort();
    }

    public int get() {
        if (port < 0) {
            throw new IllegalStateException("server port is not known yet -- the web server has not started");
        }
        return port;
    }

    /** Package-visible: lets a unit test set a port without a real WebServerInitializedEvent. */
    void setForTest(int port) {
        this.port = port;
    }
}
