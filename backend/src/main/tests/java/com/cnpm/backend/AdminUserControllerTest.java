package com.cnpm.backend;

import com.cnpm.backend.controller.AdminUserController;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.entity.AdminUserAudit;
import com.cnpm.backend.repository.AdminUserAuditRepository;
import org.mockito.ArgumentCaptor;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.never;
import static org.springframework.security.core.userdetails.User.withUsername;

class AdminUserControllerTest {
    private final AdminUserAuditRepository audit = mock(AdminUserAuditRepository.class);

    @Test
    void administratorCannotLockTheirOwnAccount() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        Authentication authentication = authentication("admin@example.test");

        AdminUserController controller = new AdminUserController(repository, audit);

        assertThatThrownBy(() -> controller.updateStatus(
                10L, new AdminUserController.UpdateUserStatusRequest(false), authentication))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(
                        ((ResponseStatusException) error).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        verify(repository, never()).save(admin);
        verifyNoInteractions(audit);
    }

    @Test
    void administratorCanDisableAnotherAccount() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        when(repository.findByIdForUpdate(11L)).thenReturn(Optional.of(target));
        when(repository.save(target)).thenReturn(target);

        var controller = new AdminUserController(repository, audit);
        var response = controller.updateStatus(
                11L, new AdminUserController.UpdateUserStatusRequest(false),
                authentication("admin@example.test"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(target.isActive()).isFalse();
        controller.updateStatus(11L, new AdminUserController.UpdateUserStatusRequest(false),
                authentication("admin@example.test"));
        assertAudit("USER_STATUS_CHANGED", "true", "false");
    }

    @Test
    void profileUpdateAuditsChangedFieldsWithoutExposingProfileValues() {
        UserRepository repository = mock(UserRepository.class);
        when(repository.findByEmail("admin@example.test"))
                .thenReturn(Optional.of(user(10L, "admin@example.test", "ADMIN")));
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findByIdForUpdate(11L)).thenReturn(Optional.of(target));
        when(repository.save(target)).thenReturn(target);

        var response = new AdminUserController(repository, audit).updateUser(
                11L, new AdminUserController.UpdateUserRequest(
                        "new-name", null, "New", "Name"), authentication("admin@example.test"));

        assertThat(response.role()).isEqualTo("DEVELOPER");
        assertThat(response.username()).isEqualTo("new-name");
        assertThat(java.util.Arrays.stream(response.getClass().getRecordComponents())
                .map(java.lang.reflect.RecordComponent::getName).toList())
                .doesNotContain("password");
        assertAudit("USER_PROFILE_CHANGED", "", "username,firstName,lastName");
    }

    @Test
    void listUsersAppliesSearchRoleAndStatusFiltersWithPagination() {
        UserRepository repository = mock(UserRepository.class);
        User target = user(11L, "developer@example.test", "DEVELOPER");
        var pageable = PageRequest.of(1, 10,
                Sort.by(Sort.Direction.DESC, "createdAt"));
        when(repository.searchForAdministration("dev", "DEVELOPER", false, pageable))
                .thenReturn(new PageImpl<>(List.of(target), pageable, 11));

        var response = new AdminUserController(repository, audit)
                .listUsers(1, 10, " dev ", "developer", false);

        assertThat(response.content()).hasSize(1);
        assertThat(response.page()).isEqualTo(1);
        assertThat(response.size()).isEqualTo(10);
        assertThat(response.totalElements()).isEqualTo(11);
        assertThat(response.totalPages()).isEqualTo(2);
        assertThat(response.content().getFirst().email()).isEqualTo("developer@example.test");
        verify(repository).searchForAdministration("dev", "DEVELOPER", false, pageable);
    }

    @Test
    void roleFilterUsesPrimaryRoleForStaffAndLegacyAdminWithoutNewEndpoint() {
        UserRepository repository = mock(UserRepository.class);
        var pageable = PageRequest.of(0, 20, Sort.by(Sort.Direction.DESC, "createdAt"));
        User staff = user(12L, "staff@example.test", "STAFF");
        User legacyAdmin = user(13L, "admin@example.test", "ADMIN");
        when(repository.searchForAdministration(null, "STAFF", null, pageable))
                .thenReturn(new PageImpl<>(List.of(staff), pageable, 1));
        when(repository.searchForAdministration(null, "ADMIN", null, pageable))
                .thenReturn(new PageImpl<>(List.of(legacyAdmin), pageable, 1));
        var controller = new AdminUserController(repository, audit);

        var staffPage = controller.listUsers(0, 20, null, "staff", null);
        var legacyAdminPage = controller.listUsers(0, 20, null, "admin", null);

        assertThat(staffPage.content()).extracting(AdminUserController.UserResponse::role)
                .containsExactly("STAFF");
        assertThat(legacyAdminPage.content()).extracting(AdminUserController.UserResponse::role)
                .containsExactly("ADMIN");
        assertThat(staffPage.totalElements()).isEqualTo(1);
        assertThat(legacyAdminPage.totalElements()).isEqualTo(1);
    }

    @Test
    void listUsersRejectsInvalidPagination() {
        UserRepository repository = mock(UserRepository.class);

        assertThatThrownBy(() -> new AdminUserController(repository, audit)
                .listUsers(0, 101, null, null, null))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(
                        ((ResponseStatusException) error).getStatusCode())
                        .isEqualTo(HttpStatus.BAD_REQUEST));
        verify(repository, never()).searchForAdministration(
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }

    @Test
    void getUserReturnsSafeDetailsWithoutPassword() {
        UserRepository repository = mock(UserRepository.class);
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findById(11L)).thenReturn(Optional.of(target));

        var response = new AdminUserController(repository, audit).getUser(11L);

        assertThat(response.id()).isEqualTo(11L);
        assertThat(response.username()).isEqualTo("developer");
        assertThat(response.role()).isEqualTo("DEVELOPER");
        assertThat(java.util.Arrays.stream(response.getClass().getRecordComponents())
                .map(java.lang.reflect.RecordComponent::getName).toList())
                .doesNotContain("password");
    }

    @Test
    void profileUpdateRejectsDuplicateEmail() {
        UserRepository repository = mock(UserRepository.class);
        when(repository.findByEmail("admin@example.test"))
                .thenReturn(Optional.of(user(10L, "admin@example.test", "ADMIN")));
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findByIdForUpdate(11L)).thenReturn(Optional.of(target));
        when(repository.existsByEmailIgnoreCaseAndIdNot("other@example.test", 11L))
                .thenReturn(true);

        assertThatThrownBy(() -> new AdminUserController(repository, audit).updateUser(
                11L, new AdminUserController.UpdateUserRequest(
                        null, "other@example.test", null, null), authentication("admin@example.test")))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(
                        ((ResponseStatusException) error).getStatusCode())
                        .isEqualTo(HttpStatus.CONFLICT));
    }

    @Test
    void administratorCanAssignOneOfTheFixedPrimaryRolesToAnotherUser() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        when(repository.findByIdForUpdate(11L)).thenReturn(Optional.of(target));
        when(repository.save(target)).thenReturn(target);

        var response = new AdminUserController(repository, audit).updatePrimaryRole(11L,
                new AdminUserController.UpdateUserRoleRequest("staff"), authentication("admin@example.test"));

        assertThat(response.role()).isEqualTo("STAFF");
        assertAudit("USER_ROLE_CHANGED", "DEVELOPER", "STAFF");
    }

    @Test
    void administratorCannotPromoteThemselfOrAssignUnknownRole() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        var controller = new AdminUserController(repository, audit);

        assertThatThrownBy(() -> controller.updatePrimaryRole(10L,
                new AdminUserController.UpdateUserRoleRequest("ADMINISTRATOR"), authentication("admin@example.test")))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> controller.updatePrimaryRole(11L,
                new AdminUserController.UpdateUserRoleRequest("UNKNOWN"), authentication("admin@example.test")))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
        verifyNoInteractions(audit);
    }

    private void assertAudit(String action, String previousValue, String newValue) {
        var entry = ArgumentCaptor.forClass(AdminUserAudit.class);
        verify(audit).save(entry.capture());
        assertThat(entry.getValue()).extracting("actorId", "targetId", "action", "previousValue", "newValue")
                .containsExactly(10L, 11L, action, previousValue, newValue);
        assertThat(entry.getValue()).extracting("occurredAt").isNotNull();
    }

    private static Authentication authentication(String email) {
        Authentication authentication = mock(Authentication.class);
        UserDetails principal = withUsername(email).password("unused")
                .roles("ADMIN").build();
        when(authentication.isAuthenticated()).thenReturn(true);
        when(authentication.getPrincipal()).thenReturn(principal);
        when(authentication.getName()).thenReturn(email);
        return authentication;
    }

    private static User user(Long id, String email, String role) {
        User user = new User(email, "encoded-password", "Test", "User", role, true);
        user.setUsername(email.substring(0, email.indexOf('@')));
        org.springframework.test.util.ReflectionTestUtils.setField(user, "id", id);
        return user;
    }
}
