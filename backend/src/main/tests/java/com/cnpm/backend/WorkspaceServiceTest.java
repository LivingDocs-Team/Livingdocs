package com.cnpm.backend;

import com.cnpm.backend.dto.WorkspaceRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.entity.Workspace;
import com.cnpm.backend.repository.WorkspaceRepository;
import com.cnpm.backend.repository.WorkspaceMembershipRepository;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.WorkspaceService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.server.ResponseStatusException;

import java.util.Optional;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class WorkspaceServiceTest {

    @Test
    void createsWorkspaceWithAuthenticatedOwnerAndStableNonLegacyIdFormat() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        User owner = user(73L);
        WorkspaceService service = service(repository);
        WorkspaceRequest request = request("Platform Docs", "Team documentation");
        when(repository.save(any(Workspace.class))).thenAnswer(invocation -> {
            Workspace saved = invocation.getArgument(0);
            ReflectionTestUtils.invokeMethod(saved, "onCreate");
            return saved;
        });

        Workspace created = service.create(owner, request);

        assertThat(created.getOwner()).isSameAs(owner);
        assertThat(created.getId()).startsWith("workspace-");
        assertThat(UUID.fromString(created.getId().substring("workspace-".length()))).isNotNull();
        assertThat(created.getId()).isNotEqualTo("ws-73");
        assertThat(created.getName()).isEqualTo("Platform Docs");
        verify(repository).save(any(Workspace.class));
    }

    @Test
    void detailAndUpdateUseOwnerScopedLookupAndReturnSameNotFoundForUnauthorizedOrMissing() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        User owner = user(73L);
        WorkspaceService service = service(repository);
        when(repository.findByIdAndOwner_Id("workspace-abc", 73L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.getForOwner(owner, "workspace-abc"))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        assertThatThrownBy(() -> service.update(owner, "workspace-abc", request("New", null)))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        verify(repository, never()).save(any(Workspace.class));
    }

    @Test
    void listIsScopedToAuthenticatedOwnersUserId() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        User owner = user(73L);
        Workspace workspace = new Workspace(owner, "Owned", null);
        when(repository.findAllByOwner_IdOrderByCreatedAtDescIdAsc(73L)).thenReturn(List.of(workspace));

        assertThat(service(repository).listForOwner(owner)).containsExactly(workspace);
        verify(repository).findAllByOwner_IdOrderByCreatedAtDescIdAsc(73L);
    }

    @Test
    void ownerCanUpdateWorkspaceDetailsWithoutChangingIdentityOrOwner() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        User owner = user(73L);
        Workspace workspace = new Workspace(owner, "Old name", "Old description");
        ReflectionTestUtils.setField(workspace, "id", "workspace-existing");
        when(repository.findByIdAndOwner_Id("workspace-existing", 73L)).thenReturn(Optional.of(workspace));
        when(repository.save(workspace)).thenReturn(workspace);

        Workspace updated = service(repository).update(
                owner, "workspace-existing", request("New name", "New description"));

        assertThat(updated.getId()).isEqualTo("workspace-existing");
        assertThat(updated.getOwner()).isSameAs(owner);
        assertThat(updated.getName()).isEqualTo("New name");
        assertThat(updated.getDescription()).isEqualTo("New description");
        verify(repository).save(workspace);
    }

    @Test
    void validatesWorkspaceNameAndDescriptionAtServiceBoundary() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        WorkspaceService service = service(repository);

        assertThatThrownBy(() -> service.create(user(73L), request("  ", null)))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> service.create(user(73L), request("Valid", "x".repeat(1001))))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
        verify(repository, never()).save(any(Workspace.class));
    }

    @Test
    void membershipAllowsMetadataReadButNotOwnerOperationsAndRemovalRevokesAccess() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        WorkspaceMembershipRepository memberships = mock(WorkspaceMembershipRepository.class);
        UserRepository users = mock(UserRepository.class);
        User owner = user(73L);
        User member = user(91L);
        Workspace workspace = new Workspace(owner, "Shared", null);
        ReflectionTestUtils.setField(workspace, "id", "workspace-shared");
        when(repository.findById("workspace-shared")).thenReturn(Optional.of(workspace));
        when(memberships.existsByWorkspace_IdAndUser_IdAndUser_ActiveTrue("workspace-shared", 91L))
                .thenReturn(true, true, false);
        when(repository.findByIdAndOwner_Id("workspace-shared", 91L)).thenReturn(Optional.empty());
        WorkspaceService service = new WorkspaceService(repository, memberships, users);

        assertThat(service.getForMemberOrOwner(member, "workspace-shared")).isSameAs(workspace);
        assertThat(service.isOwnerOrMember(91L, "workspace-shared")).isTrue();
        assertThatThrownBy(() -> service.getForOwner(member, "workspace-shared"))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        assertThat(service.isOwnerOrMember(91L, "workspace-shared")).isFalse();
    }

    @Test
    void ownerCanAddAndRemoveExistingMemberButCannotAddSelfOrDuplicate() {
        WorkspaceRepository repository = mock(WorkspaceRepository.class);
        WorkspaceMembershipRepository memberships = mock(WorkspaceMembershipRepository.class);
        UserRepository users = mock(UserRepository.class);
        User owner = user(73L);
        User member = user(91L);
        Workspace workspace = new Workspace(owner, "Shared", null);
        ReflectionTestUtils.setField(workspace, "id", "workspace-shared");
        when(repository.findByIdAndOwnerIdForUpdate("workspace-shared", 73L)).thenReturn(Optional.of(workspace));
        when(users.findById(91L)).thenReturn(Optional.of(member));
        when(memberships.existsByWorkspace_IdAndUser_Id("workspace-shared", 91L)).thenReturn(false, true);
        WorkspaceService service = new WorkspaceService(repository, memberships, users);

        assertThat(service.addMember(owner, "workspace-shared", 91L)).isSameAs(member);
        verify(memberships).save(any());
        service.removeMember(owner, "workspace-shared", 91L);
        verify(memberships).deleteByWorkspace_IdAndUser_Id("workspace-shared", 91L);
        assertThatThrownBy(() -> service.addMember(owner, "workspace-shared", 73L))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
        assertThatThrownBy(() -> service.addMember(owner, "workspace-shared", 91L))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode()).isEqualTo(HttpStatus.CONFLICT));
    }

    private static WorkspaceService service(WorkspaceRepository repository) {
        return new WorkspaceService(repository, mock(WorkspaceMembershipRepository.class), mock(UserRepository.class));
    }

    private static WorkspaceRequest request(String name, String description) {
        WorkspaceRequest request = new WorkspaceRequest();
        request.setName(name);
        request.setDescription(description);
        return request;
    }

    private static User user(long id) {
        User user = new User("owner@example.test", "unused", "Owner", "Test", "DEVELOPER", true);
        ReflectionTestUtils.setField(user, "id", id);
        return user;
    }
}



