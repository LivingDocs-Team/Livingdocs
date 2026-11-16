package com.livingdocs.github.controller;

import java.time.OffsetDateTime;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.livingdocs.github.exception.ApiException;

@RestController
public class InternalSystemAnalyticsController {
    private final JdbcTemplate jdbc;
    private final RestClient ai;

    public InternalSystemAnalyticsController(JdbcTemplate jdbc,
            @Qualifier("aiServiceRestClient") RestClient ai) {
        this.jdbc = jdbc;
        this.ai = ai;
    }

    @GetMapping("/internal/system-analytics")
    public IntegrationAnalytics analytics(
            @RequestParam("from") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam("to") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to) {
        if (!from.isBefore(to)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_RANGE", "from must be earlier than to");
        }
        AiAnalytics activity;
        try {
            activity = ai.get().uri("/internal/system-analytics?from={from}&to={to}", from, to)
                    .retrieve().body(AiAnalytics.class);
        } catch (RestClientException exception) {
            throw unavailable();
        }
        if (activity == null || activity.documentsCreated() == null
                || activity.documentVersionAuditEvents() == null || activity.aiJobs() == null
                || activity.aiJobs().completed() == null || activity.aiJobs().failed() == null
                || activity.aiJobs().observedSince() == null || activity.aiJobs().scope() == null) {
            throw unavailable();
        }
        long repositories = Objects.requireNonNull(jdbc.queryForObject("""
                SELECT count(*) FROM repositories WHERE created_at >= ? AND created_at < ?
                """, Long.class, from, to));
        long audit = Objects.requireNonNull(jdbc.queryForObject("""
                SELECT count(*) FROM document_workflow_audit WHERE created_at >= ? AND created_at < ?
                """, Long.class, from, to));
        return new IntegrationAnalytics(repositories, activity.documentsCreated(), audit,
                activity.documentVersionAuditEvents(), activity.aiJobs());
    }

    private ApiException unavailable() {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "AI_ANALYTICS_UNAVAILABLE",
                "AI service analytics are unavailable.");
    }

    public record AiJobs(Long completed, Long failed, OffsetDateTime observedSince, String scope) {}
    public record AiAnalytics(Long documentsCreated, Long documentVersionAuditEvents, AiJobs aiJobs) {}
    public record IntegrationAnalytics(long repositoriesCreated, long documentsCreated, long documentWorkflowAuditEvents,
                                       long documentVersionAuditEvents, AiJobs aiJobs) {}
}
