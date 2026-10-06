package com.example.backend.region;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class RegionStore {

    private static final Logger log = LoggerFactory.getLogger(RegionStore.class);

    private final JdbcTemplate jdbcTemplate;

    public RegionStore(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public static RegionStore noop() {
        return new RegionStore(null);
    }

    public void recordFrom(Object evidence) {
        if (jdbcTemplate == null || !(evidence instanceof Map<?, ?> map)) {
            return;
        }

        try {
            recordRegion(map);
        } catch (RuntimeException e) {
            log.atWarn()
                    .addKeyValue("event", "region_record_skipped")
                    .log("could not record region from evidence: {}", e.getMessage());
        }
    }

    private void recordRegion(Map<?, ?> evidence) {
        if (!(evidence.get("region_kind") instanceof String kind)
                || !(evidence.get("region_bbox") instanceof List<?> bbox)
                || bbox.size() != 4) {
            return;
        }

        String label = evidence.get("region_label") instanceof String text ? text : null;
        double west = ((Number) bbox.get(0)).doubleValue();
        double south = ((Number) bbox.get(1)).doubleValue();
        double east = ((Number) bbox.get(2)).doubleValue();
        double north = ((Number) bbox.get(3)).doubleValue();

        String id = label != null
                ? kind + ":" + label
                : String.format(Locale.ROOT, "%s:%.6f,%.6f,%.6f,%.6f", kind, west, south, east, north);

        jdbcTemplate.update(
                """
                INSERT INTO regions (id, kind, label, west, south, east, north, geometry, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ST_MakeEnvelope(?, ?, ?, ?, 4326), ?)
                ON CONFLICT (id) DO NOTHING
                """,
                id, kind, label, west, south, east, north, west, south, east, north, Timestamp.from(Instant.now()));
    }
}
