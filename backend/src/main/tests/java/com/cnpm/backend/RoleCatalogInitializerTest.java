package com.cnpm.backend;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;

import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.service.RoleCatalogInitializer;

class RoleCatalogInitializerTest {
    @Test
    void seedsDocumentPermissionsOnceAndDoesNotRestoreAnAssignmentRemovedLater() {
        RoleRepository roleRepository = mock(RoleRepository.class);
        PermissionRepository permissionRepository = mock(PermissionRepository.class);
        Map<String, Role> roles = new HashMap<>();
        for (String name : List.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR", "ADMIN")) {
            Role role = new Role(name, name);
            roles.put(name, role);
        }
        Map<String, Permission> storedPermissions = new HashMap<>();
        for (String code : List.of("USER_VIEW", "USER_UPDATE", "USER_DISABLE", "USER_ASSIGN_ROLE",
                "ROLE_VIEW", "PERMISSION_VIEW", "ROLE_ASSIGN_PERMISSION")) {
            storedPermissions.put(code, new Permission(code, code));
        }

        when(roleRepository.findById(org.mockito.ArgumentMatchers.anyString()))
                .thenAnswer(call -> Optional.ofNullable(roles.get(call.getArgument(0))));
        when(roleRepository.save(org.mockito.ArgumentMatchers.any(Role.class)))
                .thenAnswer(call -> {
                    Role role = call.getArgument(0);
                    roles.put(role.getName(), role);
                    return role;
                });
        when(permissionRepository.findById(org.mockito.ArgumentMatchers.anyString()))
                .thenAnswer(call -> Optional.ofNullable(storedPermissions.get(call.getArgument(0))));
        when(permissionRepository.save(org.mockito.ArgumentMatchers.any(Permission.class)))
                .thenAnswer(call -> {
                    Permission permission = call.getArgument(0);
                    storedPermissions.put(permission.getCode(), permission);
                    return permission;
                });
        when(permissionRepository.findAll()).thenAnswer(call -> new ArrayList<>(storedPermissions.values()));

        RoleCatalogInitializer initializer = new RoleCatalogInitializer(roleRepository, permissionRepository);
        initializer.run(mock(ApplicationArguments.class));

        assertThat(permissionCodes(roles.get("DEVELOPER"))).contains("DOCUMENT_CREATE", "DOCUMENT_UPDATE", "DOCUMENT_SUBMIT");
        assertThat(permissionCodes(roles.get("STAFF"))).contains("DOCUMENT_REVIEW_QUEUE_VIEW", "DOCUMENT_CLAIM", "DOCUMENT_RELEASE", "DOCUMENT_REVIEW");
        assertThat(permissionCodes(roles.get("MANAGER")))
        .contains(
                "DOCUMENT_APPROVAL_QUEUE_VIEW",
                "DOCUMENT_APPROVE",
                "DOCUMENT_REJECT",
                "DOCUMENT_ROLLBACK"
        );
        assertThat(permissionCodes(roles.get("TECHNICAL_LEAD"))).contains("DOCUMENT_TECHNICAL_REVIEW");
        assertThat(permissionCodes(roles.get("ADMINISTRATOR")))
        .contains("DOCUMENT_REASSIGN")
        .doesNotContain(
                "DOCUMENT_APPROVE",
                "DOCUMENT_REJECT",
                "DOCUMENT_ROLLBACK"
        );
        assertThat(permissionCodes(roles.get("ADMIN")))
        .contains("DOCUMENT_REASSIGN")
        .doesNotContain(
                "DOCUMENT_APPROVE",
                "DOCUMENT_REJECT",
                "DOCUMENT_ROLLBACK"
        );

        // Existing assignments are left intact; policy changes do not delete data automatically.
        roles.get("ADMINISTRATOR").getPermissions().add(storedPermissions.get("DOCUMENT_APPROVE"));
        roles.get("ADMIN").getPermissions().add(storedPermissions.get("DOCUMENT_REJECT"));

        roles.get("STAFF").getPermissions().remove(storedPermissions.get("DOCUMENT_CLAIM"));
        initializer.run(mock(ApplicationArguments.class));
        assertThat(permissionCodes(roles.get("STAFF"))).doesNotContain("DOCUMENT_CLAIM");
        assertThat(permissionCodes(roles.get("ADMINISTRATOR"))).contains("DOCUMENT_APPROVE");
        assertThat(permissionCodes(roles.get("ADMIN"))).contains("DOCUMENT_REJECT");
    }

    private static List<String> permissionCodes(Role role) {
        return role.getPermissions().stream().map(Permission::getCode).toList();
    }
}



