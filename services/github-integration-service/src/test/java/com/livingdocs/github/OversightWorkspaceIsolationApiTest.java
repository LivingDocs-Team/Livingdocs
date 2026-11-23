package com.livingdocs.github;

import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.entity.CodeEntity;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.DocumentationArtifact;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.repository.CodeEntityRepository;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentationArtifactRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.RepositorySyncService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Every /api/oversight route is limited to the repositories of the caller's workspaces. A caller reaches a
 * workspace through a WORKSPACE:&lt;id&gt; entry that the Backend adds (WORKSPACE:* for an administrator); a
 * Technical Lead has no global access unless the Backend says so.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class OversightWorkspaceIsolationApiTest {
    private static final String WS_A = "workspace-11111111-1111-1111-1111-111111111111";
    private static final String WS_B = "workspace-22222222-2222-2222-2222-222222222222";
    private static final String LEAD = "ROLE_TECHNICAL_LEAD,DOCUMENT_TECHNICAL_REVIEW";
    private static final String ADMIN = "ROLE_ADMINISTRATOR,WORKSPACE:*";
    private static final String RULES = "[{\"scope\":\"REPOSITORY\",\"target\":\"\",\"onCommit\":true,\"onPullRequest\":false}]";

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired GitHubConnectionRepository connections;
    @Autowired ConnectedRepositoryRepository repositories;
    @Autowired DocumentationArtifactRepository artifacts;
    @Autowired CodeEntityRepository codeEntities;
    @Autowired DocumentWorkflowRepository workflows;

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean RepositorySyncService repositorySyncService;

    private UUID repoA;
    private UUID repoB;
    private UUID docA;
    private UUID docB;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM documentation_code_relationships");
        jdbc.update("DELETE FROM auto_update_policies");
        codeEntities.deleteAll();
        artifacts.deleteAll();
        workflows.deleteAll();
        repositories.deleteAll();
        connections.deleteAll();

        GitHubConnection connection = new GitHubConnection();
        connection.setUserId("owner-1");
        connection.setGithubUserId(1L);
        connection.setGithubLogin("owner");
        connection.setStatus(ConnectionStatus.ACTIVE);
        connection = connections.save(connection);
        repoA = repository(connection, WS_A, 1L, "acme/alpha");
        repoB = repository(connection, WS_B, 2L, "acme/beta");
        docA = artifact(repoA, "# Alpha guide");
        docB = artifact(repoB, "# Beta secret guide");
        entity(repoA, "a");
        entity(repoB, "b");
    }

    private UUID repository(GitHubConnection connection, String workspace, long githubId, String fullName) {
        ConnectedRepository repository = new ConnectedRepository();
        repository.setWorkspaceId(workspace);
        repository.setConnectionId(connection.getId());
        repository.setGithubRepoId(githubId);
        repository.setFullName(fullName);
        repository.setDefaultBranch("main");
        repository.setHtmlUrl("https://github.com/" + fullName);
        repository.setStatus(RepositoryStatus.CONNECTED);
        return repositories.save(repository).getId();
    }

    private UUID artifact(UUID repository, String markdown) {
        DocumentationArtifact artifact = new DocumentationArtifact();
        artifact.setRepositoryId(repository);
        artifact.setOwnerUserId("owner-1");
        artifact.setGenerationJobId("job-" + repository);
        artifact.setMarkdown(markdown);
        artifact.setSourceCommit("a".repeat(40));
        return artifacts.save(artifact).getId();
    }

    private void entity(UUID repository, String key) {
        CodeEntity entity = new CodeEntity();
        entity.setRepositoryId(repository);
        entity.setStableKey(key);
        entity.setEntityType("class");
        entity.setName("Thing" + key);
        entity.setPath("src/" + key + ".java");
        entity.setLineStart(1);
        entity.setLineEnd(2);
        entity.setSourceUrl("https://github.com/acme/" + key);
        entity.setSourceCommit("a".repeat(40));
        entity.setActive(true);
        codeEntities.save(entity);
    }

    private static String member(String... workspaces) {
        StringBuilder value = new StringBuilder(LEAD);
        for (String workspace : workspaces) value.append(",WORKSPACE:").append(workspace);
        return value.toString();
    }

    @Test
    void repositoryListContainsOnlyTheCallersWorkspaces() throws Exception {
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "a").header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].fullName").value("acme/alpha"));
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "b").header("X-User-Authorities", member(WS_B)))
                .andExpect(jsonPath("$.length()").value(1)).andExpect(jsonPath("$[0].fullName").value("acme/beta"));
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "nobody").header("X-User-Authorities", LEAD))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "admin").header("X-User-Authorities", ADMIN))
                .andExpect(jsonPath("$.length()").value(2));
    }

    @Test
    void documentsListAndDetailAreScoped() throws Exception {
        mvc.perform(get("/api/oversight/documentation").header("X-User-Id", "a").header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].title").value("Alpha guide"));
        mvc.perform(get("/api/oversight/documentation/{id}", docA).header("X-User-Id", "a")
                        .header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isOk());
        // another workspace's document is not found, even with its exact id
        mvc.perform(get("/api/oversight/documentation/{id}", docB).header("X-User-Id", "a")
                        .header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/oversight/documentation/{id}", docA).header("X-User-Id", "b")
                        .header("X-User-Authorities", member(WS_B)))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/oversight/documentation/{id}", docB).header("X-User-Id", "admin")
                        .header("X-User-Authorities", ADMIN))
                .andExpect(status().isOk());
    }

    @Test
    void pullRequestsAndCommitsOfAnotherWorkspaceAreNotFound() throws Exception {
        for (String route : new String[] {"pull-requests", "commits"}) {
            mvc.perform(get("/api/oversight/repositories/{id}/" + route, repoA).header("X-User-Id", "a")
                            .header("X-User-Authorities", member(WS_A)))
                    .andExpect(status().isOk());
            mvc.perform(get("/api/oversight/repositories/{id}/" + route, repoB).header("X-User-Id", "a")
                            .header("X-User-Authorities", member(WS_A)))
                    .andExpect(status().isNotFound());
            mvc.perform(get("/api/oversight/repositories/{id}/" + route, repoA).header("X-User-Id", "b")
                            .header("X-User-Authorities", member(WS_B)))
                    .andExpect(status().isNotFound());
            mvc.perform(get("/api/oversight/repositories/{id}/" + route, repoB).header("X-User-Id", "admin")
                            .header("X-User-Authorities", ADMIN))
                    .andExpect(status().isOk());
        }
    }

    @Test
    void driftPoliciesCanOnlyBeReadAndChangedInTheCallersWorkspace() throws Exception {
        mvc.perform(get("/api/oversight/repositories/{id}/drift-policies", repoB).header("X-User-Id", "a")
                        .header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isNotFound());
        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repoB).header("X-User-Id", "a")
                        .header("X-User-Authorities", member(WS_A)).contentType(MediaType.APPLICATION_JSON).content(RULES))
                .andExpect(status().isNotFound());
        // nothing was written to the other workspace
        mvc.perform(get("/api/oversight/repositories/{id}/drift-policies", repoB).header("X-User-Id", "b")
                        .header("X-User-Authorities", member(WS_B)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));

        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repoA).header("X-User-Id", "a")
                        .header("X-User-Authorities", member(WS_A)).contentType(MediaType.APPLICATION_JSON).content(RULES))
                .andExpect(status().isOk()).andExpect(jsonPath("$[0].onCommit").value(true));
        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repoB).header("X-User-Id", "admin")
                        .header("X-User-Authorities", ADMIN).contentType(MediaType.APPLICATION_JSON).content(RULES))
                .andExpect(status().isOk());
    }

    @Test
    void healthCountsOnlyTheCallersWorkspaces() throws Exception {
        mvc.perform(get("/api/oversight/health").header("X-User-Id", "a").header("X-User-Authorities", member(WS_A)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.counts.repositories").value(1))
                .andExpect(jsonPath("$.counts.documents").value(1))
                .andExpect(jsonPath("$.counts.codeEntities").value(1));
        mvc.perform(get("/api/oversight/health").header("X-User-Id", "nobody").header("X-User-Authorities", LEAD))
                .andExpect(jsonPath("$.counts.repositories").value(0))
                .andExpect(jsonPath("$.counts.documents").value(0))
                .andExpect(jsonPath("$.counts.codeEntities").value(0));
        mvc.perform(get("/api/oversight/health").header("X-User-Id", "admin").header("X-User-Authorities", ADMIN))
                .andExpect(jsonPath("$.counts.repositories").value(2))
                .andExpect(jsonPath("$.counts.documents").value(2))
                .andExpect(jsonPath("$.counts.codeEntities").value(2));
    }

    @Test
    void aPersonalWorkspaceIsPrivateToItsOwnerAndAnUnknownWorkspaceIsDenied() throws Exception {
        GitHubConnection connection = connections.findAll().get(0);
        UUID personal = repository(connection, "ws-owner-1", 3L, "acme/personal");
        UUID unknown = repository(connection, "elsewhere", 4L, "acme/unknown");
        String lead = LEAD;
        mvc.perform(get("/api/oversight/repositories/{id}/commits", personal).header("X-User-Id", "stranger")
                        .header("X-User-Authorities", lead))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/oversight/repositories/{id}/commits", personal).header("X-User-Id", "owner-1")
                        .header("X-User-Authorities", lead))
                .andExpect(status().isOk());
        mvc.perform(get("/api/oversight/repositories/{id}/commits", unknown).header("X-User-Id", "owner-1")
                        .header("X-User-Authorities", lead))
                .andExpect(status().isNotFound());
    }

    @Test
    void everyOversightRouteRejectsACallerWithoutTheOversightPermission() throws Exception {
        String developer = "ROLE_DEVELOPER,DOCUMENT_VIEW,WORKSPACE:" + WS_A;
        for (String path : new String[] {"/api/oversight/repositories", "/api/oversight/documentation",
                "/api/oversight/health", "/api/oversight/documentation/" + docA,
                "/api/oversight/repositories/" + repoA + "/pull-requests",
                "/api/oversight/repositories/" + repoA + "/commits",
                "/api/oversight/repositories/" + repoA + "/drift-policies"}) {
            mvc.perform(get(path).header("X-User-Id", "dev").header("X-User-Authorities", developer))
                    .andExpect(status().isForbidden());
        }
        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repoA).header("X-User-Id", "dev")
                        .header("X-User-Authorities", developer).contentType(MediaType.APPLICATION_JSON).content(RULES))
                .andExpect(status().isForbidden());
    }
}
