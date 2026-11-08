package com.cnpm.backend;

import com.cnpm.backend.controller.AdminUserController;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.server.ResponseStatusException;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.springframework.security.core.userdetails.User.withUsername;

class AdminUserControllerTest {

    @Test
    void administratorCannotLockTheirOwnAccount() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        Authentication authentication = authentication("admin@example.test");

        AdminUserController controller = new AdminUserController(repository);

        assertThatThrownBy(() -> controller.updateStatus(
                10L, new AdminUserController.UpdateUserStatusRequest(false), authentication))
                .isInstanceOf(ResponseStatusException.class)
                .extracting(error -> ((ResponseStatusException) error).getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
        verify(repository, never()).save(admin);
    }

    @Test
    void administratorCanDisableAnotherAccount() {
        UserRepository repository = mock(UserRepository.class);
        User admin = user(10L, "admin@example.test", "ADMIN");
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findByEmail("admin@example.test")).thenReturn(Optional.of(admin));
        when(repository.findById(11L)).thenReturn(Optional.of(target));
        when(repository.save(target)).thenReturn(target);

        var response = new AdminUserController(repository).updateStatus(
                11L, new AdminUserController.UpdateUserStatusRequest(false),
                authentication("admin@example.test"));

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(target.isActive()).isFalse();
    }

    @Test
    void profileUpdateDoesNotChangeTheUsersRoleOrExposePassword() {
        UserRepository repository = mock(UserRepository.class);
        User target = user(11L, "developer@example.test", "DEVELOPER");
        when(repository.findById(11L)).thenReturn(Optional.of(target));
        when(repository.save(target)).thenReturn(target);

        var response = new AdminUserController(repository).updateUser(
                11L, new AdminUserController.UpdateUserRequest(
                        "new-name", null, "New", "Name"));

        assertThat(response.role()).isEqualTo("DEVELOPER");
        assertThat(response.username()).isEqualTo("new-name");
        assertThat(response.getClass().getRecordComponents())
                .extracting(component -> component.getName())
                .doesNotContain("password");
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
