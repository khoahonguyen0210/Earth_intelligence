package com.example.backend.config;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

/**
 * A servlet-level CORS filter, not WebMvcConfigurer.addCorsMappings: the
 * latter only wires CORS into Spring MVC's own RequestMappingHandlerMapping
 * (regular @RestController routes) and is silently skipped by Actuator's
 * separate handler mappings -- including the /livez and /readyz
 * "additional paths" the frontend's own health check calls
 * (management.endpoint.health.probes.add-additional-paths, in
 * application.properties). A CorsFilter runs in the servlet filter chain
 * before any handler mapping is chosen, so it covers every route
 * uniformly, actuator's included.
 */
@Configuration
public class CorsConfig {

    @Bean
    public CorsFilter corsFilter() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("http://localhost:5173"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return new CorsFilter(source);
    }
}
