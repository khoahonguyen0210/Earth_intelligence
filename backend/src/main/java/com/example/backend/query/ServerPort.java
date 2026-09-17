package com.example.backend.query;

import org.springframework.boot.web.server.context.WebServerApplicationContext;
import org.springframework.boot.web.server.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

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
