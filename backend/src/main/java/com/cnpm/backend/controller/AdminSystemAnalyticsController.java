package com.cnpm.backend.controller;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

@RestController
@PreAuthorize("hasAnyRole('ADMIN', 'ADMINISTRATOR') and @systemAdminAccess.allows(authentication)")
public class AdminSystemAnalyticsController {
    private final JdbcTemplate jdbc;
    private final RestClient integration;
    private final String secret;

    public AdminSystemAnalyticsController(JdbcTemplate jdbc, RestClient.Builder builder,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String baseUrl,
            @Value("${services.github-integration.internal-secret:}") String secret,
            @Value("${services.github-integration.connect-timeout:5s}") Duration connectTimeout,
            @Value("${services.github-integration.read-timeout:150s}") Duration readTimeout) {
        this.jdbc = jdbc;
        this.secret = secret == null ? "" : secret;
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connectTimeout);
        factory.setReadTimeout(readTimeout);
        this.integration = builder.clone().baseUrl(baseUrl).requestFactory(factory).build();
    }

    @GetMapping("/api/admin/system-analytics")
    public ResponseEntity<SystemAnalytics> analytics(
            @RequestParam("from") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam("to") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {
        if (!from.isBefore(to) || from.getNano() % 1000 != 0 || to.getNano() % 1000 != 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "from must precede to and both must use at most microsecond precision.");
        }
        if (secret.isBlank()) {
            throw unavailable();
        }
        IntegrationAnalytics activity;
        try {
            activity = integration.get().uri("/internal/system-analytics?from={from}&to={to}", from, to)
                    .headers(headers -> headers.setBearerAuth(secret))
                    .retrieve().body(IntegrationAnalytics.class);
        } catch (RestClientException exception) {
            throw unavailable();
        }
        if (activity == null || activity.repositoriesCreated() == null || activity.documentsCreated() == null
                || activity.documentWorkflowAuditEvents() == null || activity.documentVersionAuditEvents() == null
                || activity.aiJobs() == null || activity.aiJobs().completed() == null
                || activity.aiJobs().failed() == null || activity.aiJobs().observedSince() == null
                || !"CURRENT_AI_PROCESS".equals(activity.aiJobs().scope())) {
            throw unavailable();
        }
        long adminAudit = Objects.requireNonNull(jdbc.queryForObject("""
                SELECT count(*) FROM admin_user_audit WHERE occurred_at >= ? AND occurred_at < ?
                """, Long.class, from, to));
        var audit = new AuditCounts(adminAudit, activity.documentWorkflowAuditEvents(),
                activity.documentVersionAuditEvents());
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(new SystemAnalytics(
                from, to, activity.repositoriesCreated(), activity.documentsCreated(), activity.aiJobs(), audit));
    }

    private ResponseStatusException unavailable() {
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                "GitHub Integration or AI analytics are unavailable.");
    }

    public record AiJobs(Long completed, Long failed, OffsetDateTime observedSince, String scope) {}
    private record IntegrationAnalytics(Long repositoriesCreated, Long documentsCreated,
                                        Long documentWorkflowAuditEvents, Long documentVersionAuditEvents,
                                        AiJobs aiJobs) {}
    public record AuditCounts(long administration, long documentWorkflow, long documentVersion) {}
    public record SystemAnalytics(OffsetDateTime from, OffsetDateTime to, long repositoriesCreated,
                                  long documentsCreated, AiJobs aiJobs, AuditCounts audit) {}
}
