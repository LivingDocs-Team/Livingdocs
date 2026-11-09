package com.livingdocs.github.service;

import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.sync.GitHubRepositoryFetcher;
import com.livingdocs.github.sync.SyncOptions;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RepositorySyncServiceAuthorizationTest {

    @Test
    void workspaceMemberCannotSyncEvenWhenTheyOwnTheGithubConnection() {
        var repositories = mock(ConnectedRepositoryRepository.class);
        var connections = mock(GitHubConnectionService.class);
        var fetcher = mock(GitHubRepositoryFetcher.class);
        var service = new RepositorySyncService(repositories, connections, fetcher);
        UUID repositoryId = UUID.fromString("22222222-2222-2222-2222-222222222222");
        UUID connectionId = UUID.fromString("11111111-1111-1111-1111-111111111111");
        var repository = new ConnectedRepository();
        ReflectionTestUtils.setField(repository, "id", repositoryId);
        repository.setWorkspaceId("workspace-11111111-1111-1111-1111-111111111111");
        repository.setConnectionId(connectionId);
        repository.setGithubRepoId(456L);
        repository.setFullName("owner/repo");
        repository.setStatus(RepositoryStatus.CONNECTED);
        var connection = mock(GitHubConnection.class);
        when(repositories.findById(repositoryId)).thenReturn(Optional.of(repository));
        when(connections.findConnection("91")).thenReturn(Optional.of(connection));
        when(connection.getId()).thenReturn(connectionId);

        assertThatThrownBy(() -> service.sync("91", repositoryId, SyncOptions.defaults(),
                repository.getWorkspaceId(), "MEMBER"))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> org.assertj.core.api.Assertions.assertThat(exception.getStatus())
                                .isEqualTo(HttpStatus.FORBIDDEN));

        verify(fetcher, never()).fetch(org.mockito.ArgumentMatchers.anyString(),
                org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any());
        verify(connections, never()).getActiveConnection("91");
    }
}
