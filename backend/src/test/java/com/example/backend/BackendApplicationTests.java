package com.example.backend;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

// Excluding DataSourceAutoConfiguration would break JPA repository startup rather than avoid it, so it must stay enabled here.
@SpringBootTest
class BackendApplicationTests {

    @Test
    void contextLoads() {
    }

}
