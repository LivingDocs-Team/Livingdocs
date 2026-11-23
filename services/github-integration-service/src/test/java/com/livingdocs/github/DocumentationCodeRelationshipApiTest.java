package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.repository.CodeEntityRepository;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentationArtifactRepository;
import com.livingdocs.github.repository.DocumentationCodeRelationshipRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.DocumentationCodeRelationshipService;
import com.livingdocs.github.service.RepositorySyncService;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class DocumentationCodeRelationshipApiTest {
    private static final String USER = "relationship-user";
    private static final String OTHER_USER = "relationship-other";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;
    @Autowired GitHubConnectionRepository connectionRepository;
    @Autowired ConnectedRepositoryRepository repositoryRepository;
    @Autowired DocumentationArtifactRepository documentRepository;
    @Autowired CodeEntityRepository codeEntityRepository;
    @Autowired DocumentationCodeRelationshipRepository relationshipRepository;
    @Autowired DocumentationCodeRelationshipService relationshipService;

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean RepositorySyncService repositorySyncService;

    private UUID repositoryId;
    private UUID documentId;
    private UUID entityId;
    private ConnectedRepository repository; // <-- SỬA LỖI: Đưa lên làm biến instance

    @BeforeEach
    void setUp() throws Exception {
        relationshipRepository.deleteAll();
        documentRepository.deleteAll();
        codeEntityRepository.deleteAll();
        repositoryRepository.deleteAll();
        connectionRepository.deleteAll();

        GitHubConnection connection = new GitHubConnection();
        connection.setUserId(USER);
        connection.setGithubUserId(101L);
        connection.setGithubLogin("relationship-user");
        connection.setStatus(ConnectionStatus.ACTIVE);
        connection = connectionRepository.save(connection);

        repository = new ConnectedRepository(); // <-- SỬA LỖI: Gán vào biến instance, bỏ chữ ConnectedRepository
        repository.setWorkspaceId("ws-relationship-user");
        repository.setConnectionId(connection.getId());
        repository.setGithubRepoId(202L);
        repository.setFullName("acme/sample");
        repository.setDefaultBranch("main");
        repository.setHtmlUrl("https://github.com/acme/sample");
        repository.setStatus(RepositoryStatus.CONNECTED);
        repository = repositoryRepository.save(repository);
        repositoryId = repository.getId();
        when(repositorySyncService.requireOwnedRepository(eq(USER), eq(repositoryId))).thenReturn(repository);

        String analysis = """
                {"files":[{"path":"src/App.java","status":"ok",
                  "classes":[{"name":"App","lineno":2,"end_lineno":10,
                    "methods":[{"name":"run","lineno":4,"end_lineno":7}]}],
                  "functions":[],"endpoints":[]}]}
                """;
        RepositorySnapshot snapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(202L, "acme/sample", "acme", "sample", null,
                        false, false, "main", "https://github.com/acme/sample", "java", 1L, Instant.now()),
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "A", null, Instant.now(), null),
                Map.of(), List.of(new RepositorySnapshot.SourceFile("src/App.java", "blob1", 1,
                        "java", "class App {}", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.now());
        documentId = relationshipService.recordGeneration(USER, repositoryId, "job-relationship",
                objectMapper.readTree(analysis), snapshot);
        relationshipService.saveGeneratedMarkdown(USER, "job-relationship", "# Sample docs");
        entityId = codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId)
                .get(0).getId();
    }

    @Test
    void persistsAndRetrievesRelationshipsInBothDirectionsAndProvidesSourceLines() throws Exception {
        mvc.perform(get("/api/repositories/{id}/code-entities", repositoryId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].sourceUrl").value("https://github.com/acme/sample/blob/abc123/src/App.java#L2-L10"));

        List<UUID> entities = codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId)
                .stream().map(entity -> entity.getId()).toList();
        mvc.perform(put("/api/documentation/{id}/code-entities", documentId)
                        .header("X-User-Id", USER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"codeEntityIds\":[\"" + entities.get(0) + "\",\"" + entities.get(0)
                                + "\",\"" + entities.get(1) + "\"]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));

        mvc.perform(get("/api/documentation/{id}/code-entities", documentId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(2));
        mvc.perform(get("/api/documentation/code-entities/{id}/documents", entityId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(documentId.toString()))
                .andExpect(jsonPath("$[0].markdown").value("# Sample docs"));
    }

    @Test
    void reportsCodeEntitiesWithoutLinkedDocumentationAsCoverageGaps() throws Exception {
        List<UUID> entities = codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId)
                .stream().map(entity -> entity.getId()).toList();
        mvc.perform(put("/api/documentation/{id}/code-entities", documentId)
                        .header("X-User-Id", USER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"codeEntityIds\":[]}"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/repositories/{id}/coverage-gaps", repositoryId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalEntities").value(entities.size()))
                .andExpect(jsonPath("$.documentedEntities").value(0))
                .andExpect(jsonPath("$.gaps.length()").value(entities.size()))
                .andExpect(jsonPath("$.gaps[0].path").value("src/App.java"));

        mvc.perform(put("/api/documentation/{id}/code-entities", documentId)
                        .header("X-User-Id", USER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"codeEntityIds\":[\"" + entities.get(0) + "\"]}"))
                .andExpect(status().isOk());

        mvc.perform(get("/api/repositories/{id}/coverage-gaps", repositoryId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalEntities").value(entities.size()))
                .andExpect(jsonPath("$.documentedEntities").value(1))
                .andExpect(jsonPath("$.gaps.length()").value(entities.size() - 1));
    }

    @Test
    void rejectsCrossRepositoryAndMissingCodeEntityReferencesWithoutDroppingExistingLinks() throws Exception {
        relationshipService.replaceLinks(USER, documentId, List.of(entityId));
        UUID unknownEntityId = UUID.randomUUID();
        mvc.perform(put("/api/documentation/{id}/code-entities", documentId)
                        .header("X-User-Id", USER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"codeEntityIds\":[\"" + unknownEntityId + "\"]}"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/documentation/{id}/code-entities", documentId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(1));
        mvc.perform(get("/api/documentation/{id}", documentId).header("X-User-Id", OTHER_USER))
                .andExpect(status().isNotFound());
    }

    @Test
    void keepsRelationshipIdentityWhenAnAnalyzedEntityMovesToNewLines() throws Exception {
        relationshipService.replaceLinks(USER, documentId, List.of(entityId));
        String refreshedAnalysis = """
                {"files":[{"path":"src/App.java","status":"ok",
                  "classes":[{"name":"App","lineno":8,"end_lineno":20,"methods":[]}],
                  "functions":[],"endpoints":[]}]}
                """;
        RepositorySnapshot refreshedSnapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(202L, "acme/sample", "acme", "sample", null,
                        false, false, "main", "https://github.com/acme/sample", "java", 1L, Instant.now()),
                "main", new RepositorySnapshot.CommitInfo("def456", "update", "A", null, Instant.now(), null),
                Map.of(), List.of(new RepositorySnapshot.SourceFile("src/App.java", "blob2", 1,
                        "java", "class App {\n\n}", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.now());
        relationshipService.recordGeneration(USER, repositoryId, "job-next", objectMapper.readTree(refreshedAnalysis), refreshedSnapshot);

        var refreshed = codeEntityRepository.findById(entityId).orElseThrow();
        assertThat(refreshed.isActive()).isTrue();
        assertThat(refreshed.getLineStart()).isEqualTo(8);
        assertThat(refreshed.getSourceUrl())
                .isEqualTo("https://github.com/acme/sample/blob/def456/src/App.java#L8-L20");
        mvc.perform(get("/api/documentation/{id}/code-entities", documentId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(entityId.toString()));
    }

    @Test
    void hidesInactiveEntitiesFromResultsAndRestoresLinksWhenEntityReappears() throws Exception {
        relationshipService.replaceLinks(USER, documentId, List.of(entityId));

        String removedEntityAnalysis = """
                {"files":[{"path":"src/App.java","status":"ok","classes":[],"functions":[],"endpoints":[]}]}
                """;
        RepositorySnapshot emptySnapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(202L, "acme/sample", "acme", "sample", null,
                        false, false, "main", "https://github.com/acme/sample", "java", 1L, Instant.now()),
                "main", new RepositorySnapshot.CommitInfo("ghi789", "remove", "A", null, Instant.now(), null),
                Map.of(), List.of(new RepositorySnapshot.SourceFile("src/App.java", "blob3", 1,
                        "java", "", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.now());
        relationshipService.recordGeneration(USER, repositoryId, "job-removed",
                objectMapper.readTree(removedEntityAnalysis), emptySnapshot);

        assertThat(codeEntityRepository.findById(entityId).orElseThrow().isActive()).isFalse();
        mvc.perform(get("/api/documentation/{id}/code-entities", documentId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.length()").value(0));

        String restoredAnalysis = """
                {"files":[{"path":"src/App.java","status":"ok",
                  "classes":[{"name":"App","lineno":1,"end_lineno":5,
                    "methods":[{"name":"run","lineno":2,"end_lineno":4},{"name":"run","lineno":2,"end_lineno":4}]}],
                  "functions":[],"endpoints":[]}]}
                """;
        relationshipService.recordGeneration(USER, repositoryId, "job-restored",
                objectMapper.readTree(restoredAnalysis), emptySnapshot);

        assertThat(codeEntityRepository.findById(entityId).orElseThrow().isActive()).isTrue();
        mvc.perform(get("/api/documentation/{id}/code-entities", documentId).header("X-User-Id", USER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(entityId.toString()));
    }

    @Test
    void sourceUrl_fallsBackToPlainHttps_whenHtmlUrlIsNull() throws Exception {
        repository.setHtmlUrl(null);
        repositoryRepository.save(repository);

        String analysis = """
                {"files":[{"path":"src/App.java","status":"ok",
                  "classes":[{"name":"App","lineno":2,"end_lineno":10,
                    "methods":[{"name":"run","lineno":4,"end_lineno":7}]}],
                  "functions":[],"endpoints":[]}]}
                """;
        RepositorySnapshot snapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(202L, "acme/sample", "acme", "sample", null,
                        false, false, "main", null, "java", 1L, Instant.now()), // htmlUrl trong snapshot cũng null
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "A", null, Instant.now(), null),
                Map.of(), List.of(new RepositorySnapshot.SourceFile("src/App.java", "blob1", 1,
                        "java", "class App {}", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.now());
        relationshipService.recordGeneration(USER, repositoryId, "job-null-url", objectMapper.readTree(analysis), snapshot);

        var entities = codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId);
        assertThat(entities).isNotEmpty();
        String url = entities.get(0).getSourceUrl();

        assertThat(url)
                .as("Fallback URL phải là HTTPS thuần, không chứa Markdown")
                .startsWith("https://github.com/acme/sample/blob/")
                .doesNotContain("[https://github.com/]")
                .endsWith("#L2-L10");
    }

    @Test
    void sourceUrl_encodesPathAndIncludesLineFragment_whenHtmlUrlIsBlank() throws Exception {
        repository.setHtmlUrl("");
        repositoryRepository.save(repository);

        String analysis = """
                {"files":[{"path":"src/App Space.java","status":"ok",
                  "classes":[{"name":"App","lineno":2,"end_lineno":10,"methods":[]}],
                  "functions":[],"endpoints":[]}]}
                """;
        RepositorySnapshot snapshot = new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(202L, "acme/sample", "acme", "sample", null,
                        false, false, "main", "", "java", 1L, Instant.now()),
                "main", new RepositorySnapshot.CommitInfo("abc123", "test", "A", null, Instant.now(), null),
                Map.of(), List.of(new RepositorySnapshot.SourceFile("src/App Space.java", "blob1", 1,
                        "java", "class App {}", null)), List.of(),
                new RepositorySnapshot.SyncStats(1, 1, 1, 0, false, false), List.of(), Instant.now());
        relationshipService.recordGeneration(USER, repositoryId, "job-blank-url", objectMapper.readTree(analysis), snapshot);

        var entities = codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId);
        String url = entities.get(0).getSourceUrl();

        assertThat(url)
                .contains("src/App%20Space.java") 
                .endsWith("#L2-L10");             
    }
}