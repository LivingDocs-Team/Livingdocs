package com.cnpm.backend.auth;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;

class CustomUserDetailsServiceTest {

    @Test
    void disabledAccountIsNotEnabledForPasswordAuthentication() {
        UserRepository repository = mock(UserRepository.class);
        User account = new User("disabled@example.test", "encoded-password",
                "Disabled", "User", "DEVELOPER", true);
        account.setActive(false);
        when(repository.findByEmail("disabled@example.test"))
                .thenReturn(Optional.of(account));

        UserDetails details = new CustomUserDetailsService(repository)
                .loadUserByUsername("disabled@example.test");

        assertThat(details.isEnabled()).isFalse();
    }

    @Test
    void newAndExistingAccountsRemainEnabledByDefault() {
        UserRepository repository = mock(UserRepository.class);
        User account = new User("active@example.test", "encoded-password",
                "Active", "User", "DEVELOPER", true);
        when(repository.findByEmail("active@example.test"))
                .thenReturn(Optional.of(account));

        UserDetails details = new CustomUserDetailsService(repository)
                .loadUserByUsername("active@example.test");

        assertThat(details.isEnabled()).isTrue();
    }

    @Test
    void passwordAuthenticationLoadsRoleAndInheritedPermissionsWithoutRolePrefixDuplication() {
        assertPasswordAuthority("ADMINISTRATOR", "ROLE_ADMINISTRATOR", "USER_VIEW");
        assertPasswordAuthority("ADMIN", "ROLE_ADMIN", "USER_VIEW");
        assertPasswordAuthority("STAFF", "ROLE_STAFF", "DOCUMENT_REVIEW_QUEUE_VIEW");
        assertPasswordAuthority("MANAGER", "ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW");
        assertPasswordAuthority("DEVELOPER", "ROLE_DEVELOPER", "DOCUMENT_SUBMIT");
        assertPasswordAuthority("TECHNICAL_LEAD", "ROLE_TECHNICAL_LEAD", "DOCUMENT_TECHNICAL_REVIEW");
        assertPasswordAuthority("ROLE_ADMIN", "ROLE_ADMIN", "USER_VIEW");
    }

    @Test
    void passwordAuthenticationDoesNotInventPermissionsForUnknownRoleAssignments() {
        assertPasswordAuthority("STAFF", "ROLE_STAFF", null);
    }

    private void assertPasswordAuthority(String storedRole, String expectedRole, String expectedPermission) {
        UserRepository users = mock(UserRepository.class);
        RoleRepository roles = mock(RoleRepository.class);
        User account = new User("roles@example.test", "encoded-password", "Role", "User", storedRole, true);
        Role role = new Role(expectedRole.substring("ROLE_".length()), "Test role");
        if (expectedPermission != null) {
            role.getPermissions().add(new Permission(expectedPermission, "test permission"));
        }
        when(users.findByEmail("roles@example.test")).thenReturn(Optional.of(account));
        when(roles.findWithPermissionsByName(expectedRole.substring("ROLE_".length())))
                .thenReturn(Optional.of(role));

        UserDetails details = new CustomUserDetailsService(users, roles).loadUserByUsername("roles@example.test");

        assertThat(details.getAuthorities()).extracting("authority").contains(expectedRole);
        if (expectedPermission == null) {
            assertThat(details.getAuthorities()).extracting("authority").doesNotContain(
                    "DOCUMENT_REVIEW_QUEUE_VIEW", "USER_VIEW");
        } else {
            assertThat(details.getAuthorities()).extracting("authority").contains(expectedPermission);
        }
        verify(roles).findWithPermissionsByName(expectedRole.substring("ROLE_".length()));
    }
}
