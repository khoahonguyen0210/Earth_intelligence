package com.example.backend.region;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class RegionStoreTest {

    @Autowired
    private RegionStore regionStore;

    @Autowired
    private JdbcTemplate jdbc;

    private Map<String, Object> row(String id) {
        return jdbc.queryForMap(
                "select kind, label, west, south, east, north, ST_AsText(geometry) as wkt from regions where id = ?",
                id);
    }

    @Test
    void recordsANamedRegionAsARealRow() {
        String label = "test_named_" + System.nanoTime();
        Map<String, Object> evidence = Map.of(
                "region_kind", "named",
                "region_label", label,
                "region_bbox", List.of(-124.4, 32.5, -114.1, 42.0));

        regionStore.recordFrom(evidence);

        Map<String, Object> stored = row("named:" + label);
        assertEquals("named", stored.get("kind"));
        assertEquals(label, stored.get("label"));
        assertEquals(-124.4, (double) stored.get("west"), 1e-9);
        assertEquals(42.0, (double) stored.get("north"), 1e-9);
    }

    @Test
    void recordsABboxRegionWithNoLabelUsingACoordinateDerivedId() {
        Map<String, Object> evidence = Map.of(
                "region_kind", "bbox",
                "region_bbox", List.of(-120.123456, 35.654321, -119.0, 36.0));
        regionStore.recordFrom(evidence);

        Map<String, Object> stored = row("bbox:-120.123456,35.654321,-119.000000,36.000000");
        assertEquals("bbox", stored.get("kind"));
        assertNull(stored.get("label"));
    }

    @Test
    void recordingTheSameRegionTwiceUpsertsRatherThanDuplicating() {
        String label = "repeat_region_" + System.nanoTime();
        Map<String, Object> evidence = Map.of(
                "region_kind", "named", "region_label", label, "region_bbox", List.of(1.0, 2.0, 3.0, 4.0));

        regionStore.recordFrom(evidence);
        regionStore.recordFrom(evidence);

        Long count = jdbc.queryForObject("select count(*) from regions where id = ?", Long.class, "named:" + label);
        assertEquals(1L, count);
    }

    @Test
    void malformedEvidenceIsSkippedWithoutThrowing() {
        regionStore.recordFrom(Map.of("region_kind", "named")); // no region_bbox
        regionStore.recordFrom("not a map at all");
        regionStore.recordFrom(null);
    }
}
