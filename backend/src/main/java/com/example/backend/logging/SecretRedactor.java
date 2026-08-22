package com.example.backend.logging;

import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Task 13.1's "never log secrets": masks every configured secret value
 * in free text before that text reaches a log line.
 *
 * Needed because the backend logs error text that it does not write
 * itself -- a failed Python subprocess's stderr. data/firms.py builds
 * its request URL with the FIRMS map key embedded in the path
 * (build_area_url), so a Python traceback from a failed FIRMS call would
 * otherwise print the key straight into the logs. Rather than trust
 * every current and future Python error path, the backend redacts the
 * values themselves.
 *
 * The values are the same ones the process is configured with (the
 * Kubernetes Secret's keys, docs/kubernetes-manifests.md); a value
 * shorter than MIN_SECRET_LENGTH is ignored so an empty or trivially
 * short default can never turn ordinary words into "***".
 */
@Component
public class SecretRedactor {

    static final String MASK = "***";
    static final int MIN_SECRET_LENGTH = 6;
    static final int MAX_LOGGED_LENGTH = 2000;

    private final List<String> secrets;

    @Autowired
    public SecretRedactor(
            @Value("${FIRMS_MAP_KEY:}") String firmsMapKey,
            @Value("${spring.datasource.password:}") String datasourcePassword,
            @Value("${object-store.secret-key:}") String objectStoreSecretKey) {
        this(Arrays.asList(firmsMapKey, datasourcePassword, objectStoreSecretKey));
    }

    /** For callers built outside Spring (unit tests): redacts exactly `secrets`. */
    public static SecretRedactor of(String... secrets) {
        return new SecretRedactor(Arrays.asList(secrets));
    }

    SecretRedactor(List<String> secrets) {
        this.secrets = secrets.stream()
                .filter(Objects::nonNull)
                .filter(secret -> secret.length() >= MIN_SECRET_LENGTH)
                .toList();
    }

    /**
     * Returns `text` with every secret masked, truncated to
     * MAX_LOGGED_LENGTH characters so one oversized traceback cannot
     * flood a log line. Null stays null.
     */
    public String redact(String text) {
        if (text == null) {
            return null;
        }

        String redacted = text;
        for (String secret : secrets) {
            redacted = redacted.replace(secret, MASK);
        }

        if (redacted.length() > MAX_LOGGED_LENGTH) {
            return redacted.substring(0, MAX_LOGGED_LENGTH) + "...(truncated)";
        }
        return redacted;
    }
}
