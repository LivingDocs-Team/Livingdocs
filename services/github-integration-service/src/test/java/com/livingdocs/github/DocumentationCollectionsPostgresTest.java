package com.livingdocs.github;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@EnabledIfEnvironmentVariable(named = "COLLECTIONS_TEST_DB_URL", matches = ".+")
class DocumentationCollectionsPostgresTest {
    private static final String WORKSPACE = "ws-73";
    private static final String OTHER = "ws-91";
    private static final String PATH = "/api/workspaces/" + WORKSPACE + "/collections";
    private static final String LEAD = "ROLE_TECHNICAL_LEAD";
    private static final String DEVELOPER = "ROLE_DEVELOPER";

    @Autowired MockMvc mvc;
    @Autowired JdbcClient jdbc;

    @DynamicPropertySource
    static void postgres(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> System.getenv("COLLECTIONS_TEST_DB_URL"));
        registry.add("spring.datasource.username", () -> System.getenv("COLLECTIONS_TEST_DB_USER"));
        registry.add("spring.datasource.password", () -> System.getenv("COLLECTIONS_TEST_DB_PASSWORD"));
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    @Test
    void repositoryChangesRequireAnEmptyCollection() throws Exception {
        UUID original = repository(WORKSPACE, 3);
        UUID replacement = repository(WORKSPACE, 4);
        UUID document = document(original);
        String collection = """
                {"name":"Repository rules","repositoryId":"%s"}
                """.formatted(original);
        String changed = collection.replace(original.toString(), replacement.toString());
        String cleared = collection.replace("\"" + original + "\"", "null");

        mvc.perform(as(post(PATH), LEAD, WORKSPACE).contentType("application/json").content(collection))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.hasDocuments").value(false));
        UUID id = jdbc.sql("SELECT id FROM documentation_collections WHERE workspace_id = ? AND name = ?")
                .params(WORKSPACE, "Repository rules").query(UUID.class).single();
        String detail = PATH + "/" + id;
        String documentPath = detail + "/documents/" + document;
        mvc.perform(as(put(documentPath), LEAD, WORKSPACE)).andExpect(status().isNoContent());

        for (String request : new String[] { changed, cleared }) {
            mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(request))
                    .andExpect(status().isConflict());
        }
        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(collection))
                .andExpect(status().isOk()).andExpect(jsonPath("$.hasDocuments").value(true));
        mvc.perform(as(get(detail + "/documents"), LEAD, WORKSPACE))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].id").value(document.toString()));

        jdbc.sql("UPDATE repositories SET status = 'DISCONNECTED' WHERE id = ?").param(original).update();
        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(changed))
                .andExpect(status().isConflict());
        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(collection))
                .andExpect(status().isOk()).andExpect(jsonPath("$.hasDocuments").value(true));
        mvc.perform(as(delete(documentPath), LEAD, WORKSPACE)).andExpect(status().isNoContent());
        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(changed))
                .andExpect(status().isOk()).andExpect(jsonPath("$.repositoryId").value(replacement.toString()))
                .andExpect(jsonPath("$.hasDocuments").value(false));
        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json").content(cleared))
                .andExpect(status().isOk()).andExpect(jsonPath("$.repositoryId").isEmpty());
        mvc.perform(as(delete(detail), LEAD, WORKSPACE)).andExpect(status().isNoContent());
    }

    @Test
    void collectionLifecycleEnforcesRoleAndWorkspaceBoundaries() throws Exception {
        UUID repo = repository(WORKSPACE, 1);
        UUID otherRepo = repository(OTHER, 2);
        UUID document = document(repo);
        UUID otherDoc = document(otherRepo);
        String collection = """
                {"name":"API guide","description":"Reference material","repositoryId":"%s"}
                """.formatted(repo);

        mvc.perform(get(PATH)).andExpect(status().isUnauthorized());
        mvc.perform(as(get(PATH), "ROLE_STAFF", WORKSPACE)).andExpect(status().isForbidden());
        mvc.perform(as(get(PATH), DEVELOPER, OTHER)).andExpect(status().isNotFound());
        mvc.perform(as(post(PATH), DEVELOPER, WORKSPACE).contentType("application/json").content(collection))
                .andExpect(status().isForbidden());
        mvc.perform(as(post(PATH), LEAD, WORKSPACE).contentType("application/json")
                .content(collection.replace(repo.toString(), otherRepo.toString()))).andExpect(status().isNotFound());

        mvc.perform(as(post(PATH), LEAD, WORKSPACE).contentType("application/json").content(collection))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.name").value("API guide"));
        String id = jdbc.sql("SELECT id FROM documentation_collections WHERE workspace_id = ? AND name = ?")
                .params(WORKSPACE, "API guide").query(UUID.class).single().toString();
        String detail = PATH + "/" + id;
        String documentPath = detail + "/documents/" + document;

        mvc.perform(as(post(PATH), LEAD, WORKSPACE).contentType("application/json")
                .content(collection.replace("API guide", "api guide"))).andExpect(status().isConflict());
        mvc.perform(as(get(PATH), DEVELOPER, WORKSPACE)).andExpect(status().isOk())
                .andExpect(jsonPath("$[0].repositoryId").value(repo.toString()));
        mvc.perform(as(get(detail + "/document-candidates"), DEVELOPER, WORKSPACE))
                .andExpect(status().isForbidden());
        mvc.perform(as(get(detail + "/document-candidates"), LEAD, WORKSPACE)).andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("Sample document"));
        mvc.perform(as(put(detail + "/documents/" + otherDoc), LEAD, WORKSPACE)).andExpect(status().isNotFound());
        mvc.perform(as(put(documentPath), LEAD, WORKSPACE)).andExpect(status().isNoContent());
        mvc.perform(as(put(documentPath), LEAD, WORKSPACE)).andExpect(status().isNoContent());
        mvc.perform(as(put(documentPath + "/owner/73"), LEAD, WORKSPACE)
                .header("X-Verified-Document-Owner-Id", "91")).andExpect(status().isForbidden());
        mvc.perform(as(put(documentPath + "/owner/73"), LEAD, WORKSPACE)
                .header("X-Verified-Document-Owner-Id", "73")).andExpect(status().isNoContent());
        mvc.perform(as(get(detail + "/documents"), DEVELOPER, WORKSPACE)).andExpect(status().isOk())
                .andExpect(jsonPath("$[0].title").value("Sample document"))
                .andExpect(jsonPath("$[0].assignedOwnerId").value("73"));
        mvc.perform(as(delete(documentPath + "/owner"), LEAD, WORKSPACE)).andExpect(status().isNoContent());
        mvc.perform(as(put(documentPath + "/owner/73"), LEAD, WORKSPACE)
                .header("X-Verified-Document-Owner-Id", "73")).andExpect(status().isNoContent());

        mvc.perform(as(put(detail), LEAD, WORKSPACE).contentType("application/json")
                .content(collection.replace("API guide", "API reference"))).andExpect(status().isOk());
        mvc.perform(as(get(detail + "/documents"), DEVELOPER, WORKSPACE)).andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1));
        mvc.perform(as(get("/api/workspaces/" + OTHER + "/collections/" + id + "/documents"), DEVELOPER, OTHER))
                .andExpect(status().isNotFound());

        jdbc.sql("UPDATE repositories SET workspace_id = ? WHERE id = ?").params(OTHER, repo).update();
        mvc.perform(as(get(detail + "/documents"), DEVELOPER, WORKSPACE)).andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));
        mvc.perform(as(delete(detail), LEAD, WORKSPACE)).andExpect(status().isNoContent());
        org.assertj.core.api.Assertions.assertThat(jdbc.sql("""
                SELECT count(*) FROM documentation_owner_assignments WHERE workspace_id = ? AND document_id = ?
                """).params(WORKSPACE, document).query(Integer.class).single()).isEqualTo(1);
    }

    private MockHttpServletRequestBuilder as(MockHttpServletRequestBuilder request, String role, String workspace) {
        return request.header("Authorization", "Bearer test-only-internal-credential")
                .header("X-User-Authorities", role)
                .header("X-Verified-Workspace-Id", workspace)
                .header("X-Verified-Workspace-Access", "MEMBER");
    }

    private UUID repository(String workspace, long githubId) {
        UUID repository = UUID.randomUUID();
        UUID connection = UUID.randomUUID();
        jdbc.sql("""
                INSERT INTO github_connections (id, user_id, github_user_id, github_login, status, created_at, updated_at)
                VALUES (?, ?, 1, 'test-user', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """).params(connection, connection.toString()).update();
        jdbc.sql("""
                INSERT INTO repositories (id, workspace_id, connection_id, github_repo_id, full_name, status, created_at)
                VALUES (?, ?, ?, ?, 'org/repo', 'CONNECTED', CURRENT_TIMESTAMP)
                """).params(repository, workspace, connection, githubId).update();
        return repository;
    }

    private UUID document(UUID repository) {
        UUID document = UUID.randomUUID();
        jdbc.sql("""
                INSERT INTO documentation_artifacts
                    (id, repository_id, owner_user_id, generation_job_id, markdown, created_at, updated_at)
                VALUES (?, ?, '73', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """).params(document, repository, document.toString(), "# Sample document\n\nBody").update();
        return document;
    }
}
