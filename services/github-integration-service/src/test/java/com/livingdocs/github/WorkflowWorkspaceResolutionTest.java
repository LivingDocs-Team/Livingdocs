package com.livingdocs.github;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.DocumentationArtifact;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.repository.DocumentationArtifactRepository;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.DocumentationGenerationService;

/** A workflow is created only when the workspace of its document is known: it fails closed. */
class WorkflowWorkspaceResolutionTest {
    private static final String OWNER = "73";
    private static final String MANAGED = "workspace-11111111-1111-1111-1111-111111111111";
    private static final Set<String> CREATE = Set.of("DOCUMENT_CREATE", "ROLE_DEVELOPER");
    private static final Set<String> CREATE_AS_MEMBER = Set.of("DOCUMENT_CREATE", "ROLE_DEVELOPER", "WORKSPACE:" + MANAGED);
    private static final String GENERATED = "{\"id\":\"doc-1\",\"title\":\"T\",\"owner_user_id\":\"73\","
            + "\"current_version\":0,\"pending_version\":1,\"source_job_id\":\"job-1\"}";

    private DocumentWorkflowRepository workflows;
    private DocumentationGenerationService documents;
    private ConnectedRepositoryRepository repositories;
    private DocumentationArtifactRepository artifacts;
    private DocumentWorkflowService service;

    @BeforeEach
    void setUp() {
        workflows = mock(DocumentWorkflowRepository.class);
        documents = mock(DocumentationGenerationService.class);
        repositories = mock(ConnectedRepositoryRepository.class);
        artifacts = mock(DocumentationArtifactRepository.class);
        service = new DocumentWorkflowService(workflows, mock(DocumentWorkflowAuditRepository.class), documents,
                null, repositories);
        service.setArtifacts(artifacts);
        when(workflows.saveAndFlush(any(DocumentWorkflow.class))).thenAnswer(call -> call.getArgument(0));
    }

    private void document(String json) throws Exception {
        JsonNode node = new ObjectMapper().readTree(json);
        when(documents.getDocument(OWNER, "doc-1")).thenReturn(node);
    }

    private UUID repository(String workspace) {
        UUID id = UUID.randomUUID();
        ConnectedRepository repository = new ConnectedRepository();
        repository.setWorkspaceId(workspace);
        when(repositories.findById(id)).thenReturn(Optional.of(repository));
        return id;
    }

    private void artifactFor(String jobId, UUID repositoryId) {
        DocumentationArtifact artifact = new DocumentationArtifact();
        artifact.setRepositoryId(repositoryId);
        when(artifacts.findByGenerationJobId(jobId)).thenReturn(Optional.of(artifact));
    }

    private String savedWorkspace() {
        ArgumentCaptor<DocumentWorkflow> saved = ArgumentCaptor.forClass(DocumentWorkflow.class);
        verify(workflows).saveAndFlush(saved.capture());
        return saved.getValue().getWorkspaceId();
    }

    @Test
    void aDocumentGeneratedFromARepositoryOfAManagedWorkspaceBelongsToThatWorkspace() throws Exception {
        document(GENERATED);
        artifactFor("job-1", repository(MANAGED));
        service.create(OWNER, CREATE_AS_MEMBER, "doc-1");
        assertThat(savedWorkspace()).isEqualTo(MANAGED);
    }

    @Test
    void aCallerOutsideTheManagedWorkspaceCannotStartAWorkflowInIt() throws Exception {
        document(GENERATED);
        artifactFor("job-1", repository(MANAGED));
        assertThatThrownBy(() -> service.create(OWNER, CREATE, "doc-1"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(404));
        verify(workflows, never()).saveAndFlush(any());
    }

    @Test
    void theSourceSnapshotOfTheReviewedVersionIsTheFirstChoiceAndNeedsNoArtifact() throws Exception {
        UUID repositoryId = repository(MANAGED);
        document(GENERATED);
        when(documents.getExactDocumentVersion(OWNER, "doc-1", 1)).thenReturn(new ObjectMapper().readTree(
                "{\"number\":1,\"source_snapshot\":{\"repository_id\":\"" + repositoryId + "\"}}"));
        when(artifacts.findByGenerationJobId("job-1")).thenReturn(Optional.empty());
        service.create(OWNER, CREATE_AS_MEMBER, "doc-1");
        assertThat(savedWorkspace()).isEqualTo(MANAGED);
    }

    @Test
    void aSnapshotNamingARepositoryWithoutAWorkspaceIsRejected() throws Exception {
        UUID repositoryId = repository(null);
        document(GENERATED);
        when(documents.getExactDocumentVersion(OWNER, "doc-1", 1)).thenReturn(new ObjectMapper().readTree(
                "{\"number\":1,\"source_snapshot\":{\"repository_id\":\"" + repositoryId + "\"}}"));
        assertRejected();
    }

    @Test
    void aRevisionDraftTakesTheWorkspaceFromItsSourceRepository() throws Exception {
        UUID repositoryId = repository(MANAGED);
        document("{\"id\":\"doc-1\",\"title\":\"T\",\"owner_user_id\":\"73\",\"pending_version\":1,"
                + "\"pending_revision\":{\"repository_id\":\"" + repositoryId + "\"}}");
        service.create(OWNER, CREATE_AS_MEMBER, "doc-1");
        assertThat(savedWorkspace()).isEqualTo(MANAGED);
    }

    @Test
    void aDocumentNotTiedToAnyRepositoryBelongsToItsOwnerPersonalWorkspace() throws Exception {
        document("{\"id\":\"doc-1\",\"title\":\"T\",\"owner_user_id\":\"73\",\"pending_version\":1}");
        service.create(OWNER, CREATE, "doc-1");
        assertThat(savedWorkspace()).isEqualTo("ws-73");
    }

    @Test
    void aRepositoryWithoutAWorkspaceIsRejectedNotMovedIntoAPool() throws Exception {
        document(GENERATED);
        artifactFor("job-1", repository(null));
        assertRejected();
    }

    @Test
    void aMissingArtifactForTheSourceJobIsRejected() throws Exception {
        document(GENERATED);
        when(artifacts.findByGenerationJobId("job-1")).thenReturn(Optional.empty());
        assertRejected();
    }

    @Test
    void aVersionThatRecordsNoRepositoryAndHasNoArtifactBelongsToThePersonalWorkspace() throws Exception {
        document(GENERATED);
        when(documents.getExactDocumentVersion(OWNER, "doc-1", 1)).thenReturn(new ObjectMapper().readTree(
                "{\"number\":1,\"content\":\"text\"}"));
        when(artifacts.findByGenerationJobId("job-1")).thenReturn(Optional.empty());
        service.create(OWNER, CREATE, "doc-1");
        assertThat(savedWorkspace()).isEqualTo("ws-73");
    }

    @Test
    void aRepositoryThatNoLongerExistsIsRejected() throws Exception {
        document(GENERATED);
        artifactFor("job-1", UUID.randomUUID());
        assertRejected();
    }

    @Test
    void aMalformedRepositoryIdIsRejected() throws Exception {
        document("{\"id\":\"doc-1\",\"title\":\"T\",\"owner_user_id\":\"73\",\"pending_version\":1,"
                + "\"pending_revision\":{\"repository_id\":\"not-a-uuid\"}}");
        assertRejected();
    }

    private void assertRejected() {
        assertThatThrownBy(() -> service.create(OWNER, CREATE, "doc-1"))
                .isInstanceOf(ApiException.class)
                .satisfies(error -> assertThat(((ApiException) error).getStatus().value()).isEqualTo(409));
        verify(workflows, never()).saveAndFlush(any());
    }
}
