package com.example.backend.logging;

import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

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

    public static SecretRedactor of(String... secrets) {
        return new SecretRedactor(Arrays.asList(secrets));
    }

    SecretRedactor(List<String> secrets) {
        this.secrets = secrets.stream()
                .filter(Objects::nonNull)
                .filter(secret -> secret.length() >= MIN_SECRET_LENGTH)
                .toList();
    }

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
