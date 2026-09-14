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

/**
 * Durable history of the regions real requests have actually resolved to
 * -- named ("california"), a grid cell ("coordinates"), or a raw bbox --
 * read off the same evidence.region_kind/region_label/region_bbox shape
 * query.evidence.build_evidence already attaches to every analysis,
 * forecast, and Ask Earth fact (docs/persistence-schema.md's "regions"
 * table, previously schema-only). One row per distinct region: repeat
 * requests upsert the same id instead of growing this table per call.
 * Geometry is a PostGIS rectangle built with ST_MakeEnvelope, matching
 * how query.region.normalize_region already turns every region kind
 * into a bbox polygon on the Python side.
 */
@Component
public class RegionStore {

    private static final Logger log = LoggerFactory.getLogger(RegionStore.class);

    private final JdbcTemplate jdbcTemplate;

    public RegionStore(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /** A RegionStore with nothing behind it -- recordFrom is a no-op. Test convenience only. */
    public static RegionStore noop() {
        return new RegionStore(null);
    }

    /**
     * Best-effort: evidence comes from the Python subprocess boundary, so
     * a missing or malformed region shape is logged and skipped rather
     * than allowed to fail a request that already succeeded.
     */
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
