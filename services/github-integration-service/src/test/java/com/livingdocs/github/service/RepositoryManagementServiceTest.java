package com.livingdocs.github.service;

import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verifyNoInteractions;

class RepositoryManagementServiceTest {

    private static final String USER_ID = "73";
    private static final String WORKSPACE_ID = "ws-73";
    private static final long GITHUB_REPOSITORY_ID = 123L;
    private static final long CONFLICTING_REPOSITORY_ID = 456L;
    private static final UUID CONNECTION_ID =
            UUID.fromString("11111111-1111-1111-1111-111111111111");

    @Test
    void rejectsRepositoryAlreadyAssociatedWithAnotherWorkspaceInSameConnection() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        GitHubConnection connection = mock(GitHubConnection.class);
        when(connectionService.getActiveConnection(USER_ID)).thenReturn(connection);
        when(connection.getId()).thenReturn(CONNECTION_ID);
        when(connection.getAccessToken()).thenReturn("access-token");
        when(connectionRepository.findByIdForUpdate(CONNECTION_ID)).thenReturn(Optional.of(connection));
        when(gitHubClient.listAccessibleRepositories("access-token"))
                .thenReturn(List.of(availableRepository(), conflictingRepository()));
        when(repositoryRepository.existsByConnectionIdAndGithubRepoIdAndWorkspaceIdNot(
                CONNECTION_ID, CONFLICTING_REPOSITORY_ID, WORKSPACE_ID)).thenReturn(true);

        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThatThrownBy(() -> service.addRepositories(
                USER_ID, WORKSPACE_ID, List.of(GITHUB_REPOSITORY_ID, CONFLICTING_REPOSITORY_ID)))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.getStatus()).isEqualTo(HttpStatus.CONFLICT);
                    assertThat(exception.getCode()).isEqualTo("REPOSITORY_CONFLICT");
                });

        verify(repositoryRepository).existsByConnectionIdAndGithubRepoIdAndWorkspaceIdNot(
                CONNECTION_ID, CONFLICTING_REPOSITORY_ID, WORKSPACE_ID);
        verify(repositoryRepository, never()).save(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void rejectsEntireBatchBeforePersistingWhenAnyRepositoryIsNotAccessible() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        GitHubConnection connection = mock(GitHubConnection.class);
        when(connectionService.getActiveConnection(USER_ID)).thenReturn(connection);
        when(connection.getAccessToken()).thenReturn("access-token");
        when(gitHubClient.listAccessibleRepositories("access-token"))
                .thenReturn(List.of(availableRepository()));

        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThatThrownBy(() -> service.addRepositories(
                USER_ID, WORKSPACE_ID, List.of(GITHUB_REPOSITORY_ID, 999L)))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST));

        verifyNoInteractions(connectionRepository);
        verify(repositoryRepository, never()).save(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void keepsAddingAnAlreadyAssociatedRepositoryIdempotent() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        GitHubConnection connection = mock(GitHubConnection.class);
        when(connectionService.getActiveConnection(USER_ID)).thenReturn(connection);
        when(connection.getId()).thenReturn(CONNECTION_ID);
        when(connection.getAccessToken()).thenReturn("access-token");
        when(connectionRepository.findByIdForUpdate(CONNECTION_ID)).thenReturn(Optional.of(connection));
        when(gitHubClient.listAccessibleRepositories("access-token"))
                .thenReturn(List.of(availableRepository()));
        when(repositoryRepository.existsByWorkspaceIdAndConnectionIdAndGithubRepoId(
                WORKSPACE_ID, CONNECTION_ID, GITHUB_REPOSITORY_ID)).thenReturn(true);

        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThat(service.addRepositories(
                USER_ID, WORKSPACE_ID, List.of(GITHUB_REPOSITORY_ID))).isEmpty();

        verify(repositoryRepository, never())
                .existsByConnectionIdAndGithubRepoIdAndWorkspaceIdNot(
                        CONNECTION_ID, GITHUB_REPOSITORY_ID, WORKSPACE_ID);
        verify(repositoryRepository, never()).save(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void managedWorkspaceRequiresBackendVerifiedOwnerContext() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThatThrownBy(() -> service.listByWorkspace(USER_ID,
                "workspace-11111111-1111-1111-1111-111111111111", null))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> service.listByWorkspace(USER_ID,
                "workspace-11111111-1111-1111-1111-111111111111", "workspace-other"))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        verifyNoInteractions(connectionService, repositoryRepository);
    }

    @Test
    void managedWorkspaceListsOnlyWithMatchingVerifiedOwnerContext() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        var connection = mock(GitHubConnection.class);
        String workspaceId = "workspace-11111111-1111-1111-1111-111111111111";
        when(connectionService.findConnection(USER_ID)).thenReturn(Optional.of(connection));
        when(connection.getId()).thenReturn(CONNECTION_ID);
        when(repositoryRepository.findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(
                workspaceId, CONNECTION_ID)).thenReturn(List.of());
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThat(service.listByWorkspace(USER_ID, workspaceId, workspaceId)).isEmpty();
        verify(repositoryRepository).findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(
                workspaceId, CONNECTION_ID);
    }

    @Test
    void memberCanListManagedWorkspaceRepositoryMetadataWithoutOwningGitHubConnection() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        String workspaceId = "workspace-11111111-1111-1111-1111-111111111111";
        var repo = repository(UUID.fromString("22222222-2222-2222-2222-222222222222"));
        repo.setWorkspaceId(workspaceId);
        when(repositoryRepository.findByWorkspaceIdOrderByFullNameAsc(workspaceId)).thenReturn(List.of(repo));
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThat(service.listByWorkspace("91", workspaceId, workspaceId, "MEMBER"))
                .hasSize(1).first().extracting(com.livingdocs.github.dto.RepositoryResponse::id)
                .isEqualTo(repo.getId());
        verify(repositoryRepository).findByWorkspaceIdOrderByFullNameAsc(workspaceId);
        verifyNoInteractions(connectionService);
    }

    @Test
    void memberCanReadManagedRepositoryMetadataButCannotMutateOrSync() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        String workspaceId = "workspace-11111111-1111-1111-1111-111111111111";
        UUID id = UUID.fromString("22222222-2222-2222-2222-222222222222");
        var repo = repository(id);
        repo.setWorkspaceId(workspaceId);
        when(repositoryRepository.findById(id)).thenReturn(Optional.of(repo));
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThat(service.get("91", id, workspaceId, "MEMBER").id()).isEqualTo(id);
        assertThatThrownBy(() -> service.disconnect("91", id, workspaceId, "MEMBER"))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> service.addRepositories("91", workspaceId, List.of(123L), workspaceId, "MEMBER"))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> service.reassignRepository("91", workspaceId, id, workspaceId, workspaceId, "MEMBER"))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        verify(repositoryRepository, never()).delete(org.mockito.ArgumentMatchers.any());
        verify(repositoryRepository, never()).save(org.mockito.ArgumentMatchers.any());
        verifyNoInteractions(gitHubClient, connectionRepository);
    }

    @Test
    void reassignmentUpdatesExistingAssociationAndDoesNotCreateDuplicate() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        var connection = mock(GitHubConnection.class);
        UUID repositoryId = UUID.fromString("22222222-2222-2222-2222-222222222222");
        String source = "ws-73";
        String target = "workspace-11111111-1111-1111-1111-111111111111";
        var repository = new com.livingdocs.github.entity.ConnectedRepository();
        repository.setWorkspaceId(source);
        repository.setConnectionId(CONNECTION_ID);
        repository.setGithubRepoId(GITHUB_REPOSITORY_ID);
        repository.setFullName("livingdocs/example");
        repository.setStatus(com.livingdocs.github.entity.RepositoryStatus.CONNECTED);
        org.springframework.test.util.ReflectionTestUtils.setField(repository, "id", repositoryId);
        when(repositoryRepository.findById(repositoryId)).thenReturn(Optional.of(repository));
        when(connectionService.findConnection(USER_ID)).thenReturn(Optional.of(connection));
        when(connection.getId()).thenReturn(CONNECTION_ID);
        when(connectionRepository.findByIdForUpdate(CONNECTION_ID)).thenReturn(Optional.of(connection));
        when(repositoryRepository.findAllByConnectionIdAndGithubRepoIdOrderByCreatedAtAsc(
                CONNECTION_ID, GITHUB_REPOSITORY_ID)).thenReturn(List.of(repository));
        when(repositoryRepository.save(repository)).thenReturn(repository);
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        service.reassignRepository(USER_ID, target, repositoryId, target, source);

        assertThat(repository.getWorkspaceId()).isEqualTo(target);
        verify(repositoryRepository).save(repository);
    }

    @Test
    void reassignmentRejectsUnverifiedTargetAndDoesNotReadAssociation() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThatThrownBy(() -> service.reassignRepository(USER_ID,
                "workspace-11111111-1111-1111-1111-111111111111",
                UUID.randomUUID(), null, null))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.getStatus()).isEqualTo(HttpStatus.FORBIDDEN));
        verifyNoInteractions(repositoryRepository);
    }

    @Test
    void reassignmentStopsForHistoricalDuplicateRowsWithoutChangingEitherAssociation() {
        var connectionService = mock(GitHubConnectionService.class);
        var gitHubClient = mock(GitHubClient.class);
        var repositoryRepository = mock(ConnectedRepositoryRepository.class);
        var connectionRepository = mock(GitHubConnectionRepository.class);
        var connection = mock(GitHubConnection.class);
        UUID repositoryId = UUID.fromString("22222222-2222-2222-2222-222222222222");
        var existing = repository(repositoryId);
        var duplicate = repository(UUID.fromString("33333333-3333-3333-3333-333333333333"));
        duplicate.setWorkspaceId("workspace-historical-duplicate");
        when(repositoryRepository.findById(repositoryId)).thenReturn(Optional.of(existing));
        when(connectionService.findConnection(USER_ID)).thenReturn(Optional.of(connection));
        when(connection.getId()).thenReturn(CONNECTION_ID);
        when(connectionRepository.findByIdForUpdate(CONNECTION_ID)).thenReturn(Optional.of(connection));
        when(repositoryRepository.findAllByConnectionIdAndGithubRepoIdOrderByCreatedAtAsc(
                CONNECTION_ID, GITHUB_REPOSITORY_ID)).thenReturn(List.of(existing, duplicate));
        var service = new RepositoryManagementService(
                connectionService, gitHubClient, repositoryRepository, connectionRepository);

        assertThatThrownBy(() -> service.reassignRepository(USER_ID,
                "workspace-11111111-1111-1111-1111-111111111111", repositoryId,
                "workspace-11111111-1111-1111-1111-111111111111", WORKSPACE_ID))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.getStatus()).isEqualTo(HttpStatus.CONFLICT));

        assertThat(existing.getWorkspaceId()).isEqualTo(WORKSPACE_ID);
        assertThat(duplicate.getWorkspaceId()).isEqualTo("workspace-historical-duplicate");
        verify(repositoryRepository, never()).save(org.mockito.ArgumentMatchers.any());
    }

    private static GitHubRepo availableRepository() {
        return new GitHubRepo(GITHUB_REPOSITORY_ID, "livingdocs/example",
                false, "main", "https://github.com/livingdocs/example");
    }

    private static com.livingdocs.github.entity.ConnectedRepository repository(UUID id) {
        var repository = new com.livingdocs.github.entity.ConnectedRepository();
        repository.setWorkspaceId(WORKSPACE_ID);
        repository.setConnectionId(CONNECTION_ID);
        repository.setGithubRepoId(GITHUB_REPOSITORY_ID);
        repository.setFullName("livingdocs/example");
        repository.setStatus(com.livingdocs.github.entity.RepositoryStatus.CONNECTED);
        org.springframework.test.util.ReflectionTestUtils.setField(repository, "id", id);
        return repository;
    }

    private static GitHubRepo conflictingRepository() {
        return new GitHubRepo(CONFLICTING_REPOSITORY_ID, "livingdocs/other",
                false, "main", "https://github.com/livingdocs/other");
    }
}
