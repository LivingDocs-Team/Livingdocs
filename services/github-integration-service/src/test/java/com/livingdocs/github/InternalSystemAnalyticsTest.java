package com.livingdocs.github;

import java.time.OffsetDateTime;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;

import com.livingdocs.github.service.DocumentAccessService;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.queryParam;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withServiceUnavailable;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "spring.main.allow-bean-definition-overriding=true")
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
@Import(InternalSystemAnalyticsTest.AiStub.class)
class InternalSystemAnalyticsTest {
    private static final String ENDPOINT = "/internal/system-analytics";
    private static final String FROM = "2099-01-01T07:00+07:00";
    private static final String TO = "2099-01-02T07:00+07:00";
    private static final String BEARER = "Bearer test-only-internal-credential";

    @MockitoBean
    DocumentAccessService documentAccessService;

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired AiStub ai;

    @Test
    void appliesSharedAnalyticsIndexes() {
        var scripts = jdbc.queryForList("""
                SELECT "script" FROM "flyway_schema_history" WHERE "version" = '9'
                """, String.class);
        org.assertj.core.api.Assertions.assertThat(scripts).containsExactly("V9__system_analytics_indexes.sql");
    }

    @Test
    void aggregatesRecordsInWindowAndRequiresInternalCredential() throws Exception {
        UUID connection = UUID.randomUUID();
        UUID workflow = UUID.randomUUID();
        var from = OffsetDateTime.parse(FROM);
        jdbc.update("""
                INSERT INTO github_connections
                    (id, user_id, github_user_id, github_login, status, created_at, updated_at)
                VALUES (?, 'analytics-test', 101, 'test', 'ACTIVE', ?, ?)
                """, connection, from, from);
        jdbc.update("""
                INSERT INTO document_workflows
                    (id, document_id, document_title, owner_user_id, status, created_at, updated_at)
                VALUES (?, 'analytics-test', 'Test', 'analytics-test', 'DRAFT', ?, ?)
                """, workflow, from, from);
        for (var date : new OffsetDateTime[]{from.minusSeconds(1), from, OffsetDateTime.parse(TO)}) {
            jdbc.update("""
                    INSERT INTO repositories
                        (id, workspace_id, connection_id, github_repo_id, full_name, status, created_at)
                    VALUES (?, 'analytics-test', ?, ?, 'test/repo', 'CONNECTED', ?)
                    """, UUID.randomUUID(), connection, date.toEpochSecond(), date);
            jdbc.update("""
                    INSERT INTO document_workflow_audit
                        (id, workflow_id, actor_user_id, action, new_status, created_at)
                    VALUES (?, ?, 'analytics-test', 'SUBMITTED', 'SUBMITTED', ?)
                    """, UUID.randomUUID(), workflow, date);
        }

        ai.server.reset();
        mvc.perform(get(ENDPOINT).param("from", FROM).param("to", TO)
                        .header("X-User-Authorities", "ROLE_ADMINISTRATOR"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get(ENDPOINT).param("from", TO).param("to", FROM).header(HttpHeaders.AUTHORIZATION, BEARER))
                .andExpect(status().isBadRequest());

        ai.server.expect(queryParam("from", "2099-01-01T07%3A00%2B07%3A00"))
                .andRespond(withSuccess("""
                        {"documentsCreated":8,"documentVersionAuditEvents":9,
                         "aiJobs":{"completed":4,"failed":5,"observedSince":"2099-01-01T00:00:00Z",
                         "scope":"CURRENT_AI_PROCESS"}}
                        """, MediaType.APPLICATION_JSON));
        mvc.perform(get(ENDPOINT).param("from", FROM).param("to", TO).header(HttpHeaders.AUTHORIZATION, BEARER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.repositoriesCreated").value(1))
                .andExpect(jsonPath("$.documentWorkflowAuditEvents").value(1))
                .andExpect(jsonPath("$.documentsCreated").value(8))
                .andExpect(jsonPath("$.aiJobs.failed").value(5));
        ai.server.verify();
    }

    @Test
    void dependencyFailureDoesNotProduceZeroCounts() throws Exception {
        ai.server.reset();
        ai.server.expect(queryParam("to", "2099-01-02T07%3A00%2B07%3A00"))
                .andRespond(withServiceUnavailable());
        mvc.perform(get(ENDPOINT).param("from", FROM).param("to", TO).header(HttpHeaders.AUTHORIZATION, BEARER))
                .andExpect(status().isServiceUnavailable());
        ai.server.verify();
    }

    @TestConfiguration
    static class AiStub {
        private MockRestServiceServer server;

        @Bean("aiServiceRestClient")
        RestClient stub() {
            var builder = RestClient.builder().baseUrl("http://ai.example.test");
            server = MockRestServiceServer.bindTo(builder).build();
            return builder.build();
        }
    }
}