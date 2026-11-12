package com.cnpm.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.controller.AdminRoleController;
import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.repository.RoleRepository;

class AdminRoleControllerTest {
    @Test
    void rolePermissionAssignmentReplacesTheSetAndRejectsUnknownPermissions() {
        RoleRepository roles = mock(RoleRepository.class);
        PermissionRepository permissions = mock(PermissionRepository.class);
        Role role = new Role("STAFF", "Staff member");
        role.getPermissions().add(new Permission("USER_VIEW", "View users"));
        Permission update = new Permission("USER_UPDATE", "Update users");
        when(roles.findById("STAFF")).thenReturn(Optional.of(role));
        when(permissions.findAllById(org.mockito.ArgumentMatchers.<Iterable<String>>any()))
                .thenAnswer(invocation -> {
                    Iterable<String> ids = invocation.getArgument(0);
                    for (String id : ids) if (id.equals("USER_UPDATE")) return List.of(update);
                    return List.of();
                });
        when(roles.save(role)).thenReturn(role);

        var response = new AdminRoleController(roles, permissions).replacePermissions("staff",
                new AdminRoleController.PermissionAssignment(List.of("user_update")));

        assertThat(response.permissions()).containsExactly("USER_UPDATE");

        assertThatThrownBy(() -> new AdminRoleController(roles, permissions).replacePermissions("STAFF",
                new AdminRoleController.PermissionAssignment(List.of("MISSING"))))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
    }

    @Test
    void roleCatalogDoesNotAllowArbitraryOrDynamicRoles() {
        RoleRepository roles = mock(RoleRepository.class);
        assertThatThrownBy(() -> new AdminRoleController(roles, mock(PermissionRepository.class)).getRole("CUSTOM"))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
    }

    @Test
    void administratorCannotRemoveItsManagementPermissions() {
        RoleRepository roles = mock(RoleRepository.class);
        PermissionRepository permissions = mock(PermissionRepository.class);
        when(roles.findById("ADMINISTRATOR")).thenReturn(Optional.of(new Role("ADMINISTRATOR", "System administrator")));
        List<String> retainedPermissions = List.of("USER_VIEW", "USER_UPDATE", "USER_DISABLE",
                "USER_ASSIGN_ROLE", "ROLE_VIEW", "PERMISSION_VIEW", "ROLE_ASSIGN_PERMISSION");
        when(permissions.findAllById(org.mockito.ArgumentMatchers.<Iterable<String>>any()))
                .thenReturn(retainedPermissions.stream().map(code -> new Permission(code, code)).toList());

        assertThatThrownBy(() -> new AdminRoleController(roles, permissions).replacePermissions("ADMINISTRATOR",
                new AdminRoleController.PermissionAssignment(retainedPermissions)))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(error -> assertThat(((ResponseStatusException) error).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST));
    }
}
