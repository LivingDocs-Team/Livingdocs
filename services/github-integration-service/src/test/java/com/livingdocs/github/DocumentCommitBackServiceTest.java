package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.ManagerDecision;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.service.DocumentCommitBackService;
import com.livingdocs.github.service.DocumentationGenerationService;
import com.livingdocs.github.service.GitHubConnectionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class DocumentCommitBackServiceTest {
    private static final String MANAGER = "manager";
    private static final Set<String> PERMISSIONS = Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE");
    private static final UUID WORKFLOW_ID = UUID.randomUUID();
    private static final UUID REPOSITORY_ID = UUID.randomUUID();
    private static final String DOCUMENT_ID = "ab".repeat(16);
    private static final String PATH = ".livingdocs/" + DOCUMENT_ID + "-v2.md";
    private static final String SOURCE_SHA = "a1".repeat(20);
    private static final String NEXT_SHA = "b2".repeat(20);
    private static final String TREE_SHA = "c3".repeat(20);
    private static final String CONTENT = "hello\n";
    private static final String HELLO_BLOB = "ce013625030ba8dba906f756967f9e9ca394464a";

    private final DocumentWorkflowRepository workflows = mock(DocumentWorkflowRepository.class);
    private final ConnectedRepositoryRepository repositories = mock(ConnectedRepositoryRepository.class);
    private final DocumentationGenerationService documents = mock(DocumentationGenerationService.class);
    private final GitHubConnectionService connections = mock(GitHubConnectionService.class);
    private final GitHubClient github = mock(GitHubClient.class);
    private final DocumentCommitBackService service =
            new DocumentCommitBackService(workflows, repositories, documents, connections, github);

    @BeforeEach
    void approvedRevision() {
        var workflow = new DocumentWorkflow(DOCUMENT_ID, "Invoice", "owner");
        workflow.submit(2);
        workflow.decide(MANAGER, ManagerDecision.APPROVED, null);
        when(workflows.lockById(WORKFLOW_ID)).thenReturn(Optional.of(workflow));
        var json = new ObjectMapper();
        when(documents.getDocument(MANAGER, DOCUMENT_ID)).thenReturn(json.createObjectNode()
                .put("owner_user_id", "owner").put("current_version", 2));
        var version = json.createObjectNode().put("status", "accepted").put("origin", "source_change")
                .put("content", CONTENT);
        version.putObject("source_snapshot").put("repository_id", REPOSITORY_ID.toString())
                .put("repository_full_name", "acme/docs").put("commit_sha", SOURCE_SHA)
                .put("branch", "main").putNull("pull_request_number");
        when(documents.getExactDocumentVersion(MANAGER, DOCUMENT_ID, 2)).thenReturn(version);
        var repository = new ConnectedRepository();
        repository.setFullName("acme/docs");
        repository.setGithubRepoId(1L);
        repository.setDefaultBranch("main");
        repository.setStatus(RepositoryStatus.CONNECTED);
        when(repositories.lockById(REPOSITORY_ID)).thenReturn(Optional.of(repository));
        var connection = new GitHubConnection();
        connection.setAccessToken("fixture-token");
        when(connections.getActiveConnection(MANAGER)).thenReturn(connection);
    }

    @Test
    void publishesExactApprovedBytesAtExpectedSourceHead() {
        tree(SOURCE_SHA, List.of());
        when(github.commitFileOnBranch("fixture-token", "fixture-ref", SOURCE_SHA, PATH,
                CONTENT.getBytes(StandardCharsets.UTF_8), "Publish LivingDocs document " + DOCUMENT_ID + " v2"))
                .thenReturn(NEXT_SHA);
        assertThat(service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 2))
                .isEqualTo(new DocumentCommitBackService.Result(PATH, NEXT_SHA, false));
    }

    @Test
    void retryReturnsExistingIdenticalPublicationWithoutWriting() {
        tree(NEXT_SHA, List.of(new GitHubTree.Entry(PATH, "100644", "blob", HELLO_BLOB, 6L)));
        assertThat(service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 2))
                .isEqualTo(new DocumentCommitBackService.Result(PATH, NEXT_SHA, true));
        assertNoWrite();
    }

    @Test
    void staleBranchOrOccupiedPathCannotWrite() {
        tree(NEXT_SHA, List.of());
        assertThatThrownBy(() -> service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 2))
                .hasMessageContaining("branch advanced");
        tree(SOURCE_SHA, List.of(new GitHubTree.Entry(PATH, "100644", "blob", HELLO_BLOB, 6L)));
        assertThatThrownBy(() -> service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 2))
                .hasMessageContaining("occupies the publication path");
        assertNoWrite();
    }

    @Test
    void validatesManagerIdentityPermissionAndApprovedVersionBeforeCallingGitHub() {
        assertThatThrownBy(() -> service.commit(MANAGER, Set.of("ROLE_MANAGER"), WORKFLOW_ID, 2))
                .hasMessageContaining("permission");
        assertThatThrownBy(() -> service.commit("other-manager", PERMISSIONS, WORKFLOW_ID, 2))
                .hasMessageContaining("approving manager");
        assertThatThrownBy(() -> service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 1))
                .hasMessageContaining("version is not approved");
        verifyNoInteractions(github);
    }

    @Test
    void githubWriteDenialSurfacesAsForbidden() {
        tree(SOURCE_SHA, List.of());
        when(github.commitFileOnBranch("fixture-token", "fixture-ref", SOURCE_SHA, PATH,
                CONTENT.getBytes(StandardCharsets.UTF_8), "Publish LivingDocs document " + DOCUMENT_ID + " v2"))
                .thenThrow(new GitHubApiException("fixture denial", 403, HttpHeaders.EMPTY, ""));
        assertThatThrownBy(() -> service.commit(MANAGER, PERMISSIONS, WORKFLOW_ID, 2))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void githubMutationUsesTheVerifiedRefAndCompareAndSwapHead() {
        var builder = RestClient.builder();
        var fakeGitHub = MockRestServiceServer.bindTo(builder).build();
        fakeGitHub.expect(org.springframework.test.web.client.match.MockRestRequestMatchers
                        .requestTo("http://github.test/graphql"))
                .andExpect(org.springframework.test.web.client.match.MockRestRequestMatchers
                        .header("Authorization", "Bearer fixture-token"))
                .andExpect(org.springframework.test.web.client.match.MockRestRequestMatchers.content().json("""
                        {"variables":{"input":{
                          "expectedHeadOid":"%s",
                          "branch":{"id":"fixture-ref"},
                          "message":{"headline":"Publish"},
                          "fileChanges":{"additions":[{"path":"%s","contents":"aGVsbG8K"}]}
                        }}}
                        """.formatted(SOURCE_SHA, PATH)))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess("""
                        {"data":{"createCommitOnBranch":{"commit":{"oid":"%s"}}}}
                        """.formatted(NEXT_SHA), MediaType.APPLICATION_JSON));
        var client = new GitHubClient(new GitHubProperties(null, null, null, null,
                "http://github.test", "http://github.test"), builder);
        assertThat(client.commitFileOnBranch("fixture-token", "fixture-ref", SOURCE_SHA, PATH,
                CONTENT.getBytes(StandardCharsets.UTF_8), "Publish")).isEqualTo(NEXT_SHA);
        fakeGitHub.verify();
    }

    private void tree(String head, List<GitHubTree.Entry> entries) {
        when(github.getPublicationBranch("fixture-token", "acme", "docs"))
                .thenReturn(new GitHubClient.PublicationBranch(1L, "acme/docs", "fixture-ref", "main", head, TREE_SHA));
        when(github.getTree("fixture-token", "acme", "docs", TREE_SHA))
                .thenReturn(new GitHubTree(TREE_SHA, false, entries));
    }

    private void assertNoWrite() {
        org.mockito.Mockito.verify(github, org.mockito.Mockito.never()).commitFileOnBranch(
                org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.anyString());
    }
}
