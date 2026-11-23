package com.cnpm.backend.controller;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@RestController
@RequestMapping("/api/admin/health")
@PreAuthorize("hasAnyRole('ADMIN', 'ADMINISTRATOR') and @systemAdminAccess.allows(authentication)")
public class AdminHealthController {

    private final JdbcTemplate jdbc;
    private final RestClient integrationClient;

    public AdminHealthController(
            JdbcTemplate jdbc,
            RestClient.Builder builder,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String baseUrl) {
        this.jdbc = jdbc;
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(2));
        factory.setReadTimeout(Duration.ofSeconds(5));
        this.integrationClient = builder.clone().baseUrl(baseUrl.replaceAll("/+$", "")).requestFactory(factory).build();
    }

    @GetMapping
    public ResponseEntity<HealthReport> health() {
        List<ServiceHealth> services = new ArrayList<>();
        services.add(new ServiceHealth("backend", "Backend API", "UP", 200, 0L, "Reachable"));
        services.add(probeDatabase());
        services.addAll(probeGitHubIntegration());

        boolean allUp = services.stream().allMatch(s -> "UP".equals(s.status()));
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new HealthReport(allUp ? "UP" : "DEGRADED", OffsetDateTime.now(), services));
    }

    private ServiceHealth probeDatabase() {
        long start = System.nanoTime();
        try {
            Integer result = jdbc.queryForObject("SELECT 1", Integer.class);
            long ms = Duration.ofNanos(System.nanoTime() - start).toMillis();
            if (result != null && result == 1) {
                return new ServiceHealth("database", "Backend Database", "UP", 200, ms, "PostgreSQL reachable");
            }
            return new ServiceHealth("database", "Backend Database", "DOWN", 200, ms, "Unexpected query result");
        } catch (Exception ex) {
            long ms = Duration.ofNanos(System.nanoTime() - start).toMillis();
            return new ServiceHealth("database", "Backend Database", "DOWN", null, ms, "Database check failed");
        }
    }

    private List<ServiceHealth> probeGitHubIntegration() {
        long start = System.nanoTime();
        try {
            var entity = integrationClient.get()
                    .uri("/actuator/health")
                    .retrieve()
                    .toEntity(Map.class);
            long ms = Duration.ofNanos(System.nanoTime() - start).toMillis();
            int code = entity.getStatusCode().value();
            Map<?, ?> body = entity.getBody();
            String rawStatus = body != null && body.get("status") != null ? String.valueOf(body.get("status")) : "";
            boolean up = entity.getStatusCode().is2xxSuccessful() && "UP".equalsIgnoreCase(rawStatus);

            List<ServiceHealth> list = new ArrayList<>();
            list.add(new ServiceHealth(
                    "github-integration",
                    "GitHub Integration Service",
                    up ? "UP" : "DOWN",
                    code,
                    ms,
                    up ? "UP" : "Health payload status: " + (rawStatus.isBlank() ? "missing" : rawStatus)));

            Object componentsObj = body != null ? body.get("components") : null;
            if (componentsObj instanceof Map<?, ?> components) {
                list.add(extractComponent(components, "aiService", "AI Service", ms));
                list.add(extractComponent(components, "codeAnalyzer", "Code Analyzer", ms));
            }
            return list;
        } catch (RestClientResponseException ex) {
            long ms = Duration.ofNanos(System.nanoTime() - start).toMillis();
            return List.of(new ServiceHealth(
                    "github-integration",
                    "GitHub Integration Service",
                    "DOWN",
                    ex.getStatusCode().value(),
                    ms,
                    "Health endpoint returned HTTP " + ex.getStatusCode().value()));
        } catch (RestClientException ex) {
            long ms = Duration.ofNanos(System.nanoTime() - start).toMillis();
            return List.of(new ServiceHealth(
                    "github-integration",
                    "GitHub Integration Service",
                    "DOWN",
                    null,
                    ms,
                    "Health endpoint unavailable"));
        }
    }

    private ServiceHealth extractComponent(Map<?, ?> components, String key, String label, long fallbackMs) {
        Object raw = components.get(key);
        if (raw instanceof Map<?, ?> map && map.get("status") != null) {
            String status = String.valueOf(map.get("status")).toUpperCase();
            return new ServiceHealth(key, label, "UP".equals(status) ? "UP" : "DOWN", 200, fallbackMs, status);
        }
        return new ServiceHealth(key, label, "DOWN", null, fallbackMs, "Component status unavailable");
    }

    public record ServiceHealth(
            String id,
            String name,
            String status,
            Integer httpStatus,
            Long latencyMs,
            String detail) {}

    public record HealthReport(
            String status,
            OffsetDateTime checkedAt,
            List<ServiceHealth> services) {}
}