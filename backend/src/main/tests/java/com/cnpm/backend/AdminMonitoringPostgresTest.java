package com.cnpm.backend;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.UUID;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class AdminMonitoringPostgresTest {
    private static final String POLICIES = "/api/admin/notification-policies";
    private static final String ANALYTICS = "/api/admin/system-analytics";
    private static final String SECRET = "test-monitoring-secret";
    private static final HttpServer integration = integrationStub();

    @Autowired MockMvc mvc;
    @Autowired UserRepository users;
    @Autowired JdbcTemplate jdbc;

    @DynamicPropertySource
    static void configureIntegration(DynamicPropertyRegistry properties) {
        properties.add("services.github-integration.base-url",
                () -> "http://127.0.0.1:" + integration.getAddress().getPort());
        properties.add("services.github-integration.internal-secret", () -> SECRET);
    }

    @AfterAll
    static void stopIntegration() {
        integration.stop(0);
    }

    @Test
    void policiesRequireAdminAndCsrfAndPersistUpdates() throws Exception {
        String adminEmail = account("ADMINISTRATOR");
        var admin = user(adminEmail).roles("ADMINISTRATOR");
        var developer = user(account("DEVELOPER")).roles("DEVELOPER");
        String route = POLICIES + "/AI_JOB_FAILED";
        String create = """
                {"recipients":["alerts@example.test","ops@example.test","alerts@example.test"],"enabled":true}
                """;

        mvc.perform(get(POLICIES)).andExpect(status().isUnauthorized());
        mvc.perform(get(POLICIES).with(developer)).andExpect(status().isForbidden());
        mvc.perform(put(route).with(developer).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(create))
                .andExpect(status().isForbidden());
        mvc.perform(put(route).with(admin).contentType(MediaType.APPLICATION_JSON).content(create))
                .andExpect(status().isForbidden());
        mvc.perform(put(route).with(admin).with(csrf()).contentType(MediaType.APPLICATION_JSON)
                .content("{\"recipients\":[\"invalid\"],\"enabled\":true}")).andExpect(status().isBadRequest());
        mvc.perform(put(POLICIES + "/UNKNOWN").with(admin).with(csrf())
                .contentType(MediaType.APPLICATION_JSON).content(create)).andExpect(status().isBadRequest());
        mvc.perform(put(route).with(admin).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(create))
                .andExpect(status().isOk()).andExpect(jsonPath("$.recipients.length()").value(2))
                .andExpect(jsonPath("$.enabled").value(true));
        mvc.perform(put(route).with(admin).with(csrf()).contentType(MediaType.APPLICATION_JSON)
                .content("{\"recipients\":[\"ops@example.test\"],\"enabled\":false}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.enabled").value(false));
        mvc.perform(get(POLICIES).with(admin)).andExpect(status().isOk())
                .andExpect(jsonPath("$.policies[*].event", hasItem("AI_JOB_FAILED")));
        assertThat(jdbc.queryForMap("""
                SELECT recipients[1] AS recipient, enabled FROM notification_policies WHERE event = 'AI_JOB_FAILED'
                """)).containsEntry("recipient", "ops@example.test").containsEntry("enabled", false);
        mvc.perform(delete(route).with(admin).with(csrf())).andExpect(status().isNoContent());
        mvc.perform(delete(route).with(admin).with(csrf())).andExpect(status().isNoContent());
        Long actorId = users.findByEmail(adminEmail).orElseThrow().getId();
        assertThat(jdbc.queryForList("""
                SELECT action FROM admin_user_audit
                WHERE actor_id = ? AND target_event = 'AI_JOB_FAILED' ORDER BY id
                """, String.class, actorId)).containsExactly(
                "NOTIFICATION_POLICY_SAVED", "NOTIFICATION_POLICY_SAVED", "NOTIFICATION_POLICY_DELETED");
        mvc.perform(get(POLICIES).with(admin)).andExpect(status().isOk())
                .andExpect(jsonPath("$.policies[*].event", not(hasItem("AI_JOB_FAILED"))));
    }

    @Test
    void analyticsUsesHalfOpenWindowAndRejectsAStaleAdminSession() throws Exception {
        String admin = account("ADMINISTRATOR");
        var sessionRole = user(admin).roles("ADMINISTRATOR");
        String from = "2099-01-01T07:00:00+07:00";
        String to = "2099-01-02T07:00:00+07:00";
        for (String instant : new String[]{from, to, "2098-12-31T23:59:59.999999Z"}) {
            jdbc.update("""
                    INSERT INTO admin_user_audit (actor_id, target_id, action, previous_value, new_value, occurred_at)
                    VALUES (101, 102, 'USER_ROLE_CHANGED', 'DEVELOPER', 'STAFF', ?)
                    """, OffsetDateTime.parse(instant));
        }
        mvc.perform(get(ANALYTICS).param("from", from).param("to", to))
                .andExpect(status().isUnauthorized());
        mvc.perform(get(ANALYTICS).param("from", from).param("to", to).with(sessionRole))
                .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.repositoriesCreated").value(2))
                .andExpect(jsonPath("$.documentsCreated").value(3))
                .andExpect(jsonPath("$.aiJobs.completed").value(4))
                .andExpect(jsonPath("$.aiJobs.failed").value(5))
                .andExpect(jsonPath("$.aiJobs.scope").value("CURRENT_AI_PROCESS"))
                .andExpect(jsonPath("$.audit.administration").value(1))
                .andExpect(jsonPath("$.audit.documentWorkflow").value(6))
                .andExpect(jsonPath("$.audit.documentVersion").value(7));
        mvc.perform(get(ANALYTICS).param("from", to).param("to", from).with(sessionRole))
                .andExpect(status().isBadRequest());
        mvc.perform(get(ANALYTICS).param("from", from).param("to", "2099-01-03T00:00:00Z").with(sessionRole))
                .andExpect(status().isServiceUnavailable());

        var demoted = users.findByEmail(admin).orElseThrow();
        demoted.setRole("DEVELOPER");
        users.saveAndFlush(demoted);
        mvc.perform(get(ANALYTICS).param("from", from).param("to", to).with(sessionRole))
                .andExpect(status().isForbidden());
        mvc.perform(get(POLICIES).with(sessionRole)).andExpect(status().isForbidden());
    }

    private String account(String role) {
        String username = UUID.randomUUID().toString();
        String email = username + "@example.test";
        var account = new User(email, "unused-password", "Test", "User", role, true);
        account.setUsername(username);
        users.saveAndFlush(account);
        return email;
    }

    private static HttpServer integrationStub() {
        try {
            var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/internal/system-analytics", exchange -> {
                try (exchange) {
                    String query = exchange.getRequestURI().getRawQuery();
                    if (!("Bearer " + SECRET).equals(exchange.getRequestHeaders().getFirst("Authorization"))
                            || !query.contains("%2B07") || query.contains("2099-01-03")) {
                        exchange.sendResponseHeaders(503, -1);
                        return;
                    }
                    byte[] body = """
                            {"repositoriesCreated":2,"documentsCreated":3,"documentWorkflowAuditEvents":6,
                             "documentVersionAuditEvents":7,"aiJobs":{"completed":4,"failed":5,
                             "observedSince":"2099-01-01T00:00:00Z","scope":"CURRENT_AI_PROCESS"}}
                            """.getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type", "application/json");
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                }
            });
            server.start();
            return server;
        } catch (java.io.IOException exception) {
            throw new java.io.UncheckedIOException(exception);
        }
    }
}
