package com.cnpm.backend.controller;

import java.time.Duration;
import java.math.BigDecimal;
import java.util.Map;

import com.cnpm.backend.service.SystemConfigurationService;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/admin/system-config")
@PreAuthorize("hasAnyRole('ADMIN', 'ADMINISTRATOR') and @systemAdminAccess.allows(authentication)")
public class AdminSystemConfigController {

    private final SystemConfigurationService configuration;
    private final String frontendUrl;
    private final boolean sessionCookieSecure;
    private final String sessionCookieSameSite;
    private final boolean githubOAuthConfigured;
    private final String githubIntegrationBaseUrl;
    private final boolean internalSecretConfigured;
    private final long connectTimeoutSeconds;
    private final long readTimeoutSeconds;

    public AdminSystemConfigController(
            SystemConfigurationService configuration,
            @Value("${app.frontend-url:http://localhost:5173}") String frontendUrl,
            @Value("${server.servlet.session.cookie.secure:false}") boolean sessionCookieSecure,
            @Value("${server.servlet.session.cookie.same-site:Lax}") String sessionCookieSameSite,
            Environment environment,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String githubIntegrationBaseUrl,
            @Value("${services.github-integration.internal-secret:}") String internalSecret,
            @Value("${services.github-integration.connect-timeout:5s}") Duration connectTimeout,
            @Value("${services.github-integration.read-timeout:150s}") Duration readTimeout) {
        this.configuration = configuration;
        this.frontendUrl = frontendUrl;
        this.sessionCookieSecure = sessionCookieSecure;
        this.sessionCookieSameSite = sessionCookieSameSite;
        this.githubOAuthConfigured = githubOAuthConfigured(environment);
        this.githubIntegrationBaseUrl = githubIntegrationBaseUrl;
        this.internalSecretConfigured = internalSecret != null && !internalSecret.isBlank();
        this.connectTimeoutSeconds = connectTimeout.toSeconds();
        this.readTimeoutSeconds = readTimeout.toSeconds();
    }

    /**
     * application.properties maps the client id to ${SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_GITHUB_CLIENT_ID}
     * with no default. @Value fails on that unset variable; the Binder (as the OAuth2 client itself does) keeps
     * it as the literal "${...}", which means "not configured".
     */
    static boolean githubOAuthConfigured(Environment environment) {
        String clientId = Binder.get(environment)
                .bind("spring.security.oauth2.client.registration.github.client-id", String.class)
                .orElse("");
        return !clientId.isBlank() && !clientId.startsWith("${") && !"local-placeholder".equals(clientId);
    }

    @GetMapping
    public SystemConfigResponse getConfig() {
        return new SystemConfigResponse(
                new AuditConfig(configuration.getAuditLogRetentionDays(), "0 0 0 * * * UTC"),
                new SecurityConfigSummary(frontendUrl, sessionCookieSecure, sessionCookieSameSite, githubOAuthConfigured),
                new IntegrationConfigSummary(
                        githubIntegrationBaseUrl,
                        internalSecretConfigured,
                        connectTimeoutSeconds,
                        readTimeoutSeconds));
    }

    @PatchMapping
    public SystemConfigResponse updateConfig(@RequestBody UpdateSystemConfigRequest request, Authentication authentication) {
        if (request == null || request.auditRetentionDays() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "auditRetentionDays is required");
        }
        configuration.update("retention", Map.of(SystemConfigurationService.AUDIT_RETENTION_KEY,
                request.auditRetentionDays()), authentication.getName());
        return getConfig();
    }

    public record UpdateSystemConfigRequest(BigDecimal auditRetentionDays) {}
    public record AuditConfig(int retentionDays, String purgeSchedule) {}
    public record SecurityConfigSummary(
            String frontendUrl,
            boolean sessionCookieSecure,
            String sessionCookieSameSite,
            boolean githubOAuthConfigured) {}
    public record IntegrationConfigSummary(
            String githubIntegrationBaseUrl,
            boolean internalSecretConfigured,
            long connectTimeoutSeconds,
            long readTimeoutSeconds) {}
    public record SystemConfigResponse(
            AuditConfig audit,
            SecurityConfigSummary security,
            IntegrationConfigSummary integration) {}
}