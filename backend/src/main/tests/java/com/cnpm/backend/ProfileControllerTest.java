package com.cnpm.backend;

import com.cnpm.backend.controller.ProfileController;
import com.cnpm.backend.controller.ProfileController.NotificationPreferences;
import com.cnpm.backend.controller.ProfileController.ProfileResponse;
import com.cnpm.backend.controller.ProfileController.UpdateProfileRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.core.userdetails.User.withUsername;

/** LD-52: profile (LD-49, LD-50) and notification preferences (LD-51) of the signed-in user. */
class ProfileControllerTest {

    private UserRepository repository;
    private ProfileController controller;
    private User user;
    private Authentication signedIn;

    @BeforeEach
    void setUp() {
        repository = mock(UserRepository.class);
        controller = new ProfileController(repository);
        user = new User("dev@example.test", "encoded-password", "Hai", "Dang", "DEVELOPER", true);
        user.setUsername("dev");
        org.springframework.test.util.ReflectionTestUtils.setField(user, "id", 7L);
        when(repository.findByEmail("dev@example.test")).thenReturn(Optional.of(user));
        when(repository.save(user)).thenReturn(user);
        signedIn = authentication("dev@example.test");
    }

    // ------------------------------------------------------------------ LD-49: view profile

    @Test
    void profileOfTheSignedInUser_hasNoPassword() {
        ResponseEntity<?> response = controller.getProfile(signedIn);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo(new ProfileResponse(7L, "dev", "dev@example.test", "Hai", "Dang", "DEVELOPER"));
        assertThat(java.util.Arrays.stream(ProfileResponse.class.getRecordComponents())
                .map(java.lang.reflect.RecordComponent::getName).toList())
                .doesNotContain("password");
    }

    @Test
    void gitHubUserIsFoundByGitHubId() {
        user.setGithubId("9200");
        when(repository.findByGithubId("9200")).thenReturn(Optional.of(user));
        Authentication github = mock(Authentication.class);
        when(github.isAuthenticated()).thenReturn(true);
        when(github.getPrincipal()).thenReturn(new DefaultOAuth2User(List.of(), Map.of("id", 9200, "login", "d3r-bbb"), "login"));

        assertThat(((ProfileResponse) controller.getProfile(github).getBody()).username()).isEqualTo("dev");
    }

    @Test
    void unknownOrMissingUser_isUnauthorized() {
        assertThat(controller.getProfile(null).getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(controller.getProfile(authentication("gone@example.test")).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(controller.updateNotificationPreferences(new NotificationPreferences(true, true, true, true), null)
                .getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    // ------------------------------------------------------------------ LD-50: update profile

    @Test
    void updateTrimsTheGivenFields_andKeepsTheOthers() {
        ResponseEntity<?> response = controller.updateProfile(new UpdateProfileRequest("  dang  ", " Le Hien ", null), signedIn);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(user.getUsername()).isEqualTo("dang");
        assertThat(user.getFirstName()).isEqualTo("Le Hien");
        assertThat(user.getLastName()).isEqualTo("Dang");
        assertThat(user.getEmail()).isEqualTo("dev@example.test");
        assertThat(user.getRole()).isEqualTo("DEVELOPER");
        verify(repository).save(user);
    }

    @Test
    void invalidFields_areRejected_andNothingIsSaved() {
        assertError(controller.updateProfile(new UpdateProfileRequest(" ", null, null), signedIn),
                HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Username must contain 1 to 50 characters.");
        assertError(controller.updateProfile(new UpdateProfileRequest("x".repeat(51), null, null), signedIn),
                HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Username must contain 1 to 50 characters.");
        assertError(controller.updateProfile(new UpdateProfileRequest("ok", "New", " "), signedIn),
                HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Last name must contain 1 to 100 characters.");
        assertError(controller.updateProfile(new UpdateProfileRequest(null, "y".repeat(101), null), signedIn),
                HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "First name must contain 1 to 100 characters.");
        assertError(controller.updateProfile(null, signedIn),
                HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Request body is required.");

        assertThat(user.getFirstName()).isEqualTo("Hai");  // "New" was not applied either
        verify(repository, never()).save(any());
    }

    @Test
    void usernameOfAnotherUser_isRejected() {
        when(repository.existsByUsernameIgnoreCaseAndIdNot("Taken", 7L)).thenReturn(true);

        assertError(controller.updateProfile(new UpdateProfileRequest("Taken", null, null), signedIn),
                HttpStatus.CONFLICT, "USERNAME_TAKEN", "Username is already in use.");
        assertThat(user.getUsername()).isEqualTo("dev");
        verify(repository, never()).save(any());
    }

    // ------------------------------------------------------------------ LD-51: notification preferences

    @Test
    void preferencesAreOnByDefault_andCanBeSavedAndReadBack() {
        assertThat(controller.getNotificationPreferences(signedIn).getBody())
                .isEqualTo(new NotificationPreferences(true, true, true, true));

        ResponseEntity<?> saved = controller.updateNotificationPreferences(
                new NotificationPreferences(false, true, false, true), signedIn);

        assertThat(saved.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(saved.getBody()).isEqualTo(new NotificationPreferences(false, true, false, true));
        assertThat(user.isNotificationEnabled()).isFalse();
        assertThat(user.isNotifyReviewRequests()).isFalse();
        assertThat(controller.getNotificationPreferences(signedIn).getBody())
                .isEqualTo(new NotificationPreferences(false, true, false, true));
    }

    @Test
    void missingPreference_isRejected_andNothingIsSaved() {
        assertError(controller.updateNotificationPreferences(new NotificationPreferences(false, null, true, true), signedIn),
                HttpStatus.BAD_REQUEST, "PREFERENCES_INVALID",
                "emailUpdates, documentChanges, reviewRequests and systemNotifications are required.");
        assertThat(controller.updateNotificationPreferences(null, signedIn).getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);

        assertThat(user.isNotificationEnabled()).isTrue();
        verify(repository, never()).save(any());
    }

    private static void assertError(ResponseEntity<?> response, HttpStatus status, String code, String message) {
        assertThat(response.getStatusCode()).isEqualTo(status);
        assertThat(response.getBody()).isEqualTo(Map.of("status", status.value(), "code", code, "message", message));
    }

    private static Authentication authentication(String email) {
        Authentication authentication = mock(Authentication.class);
        UserDetails principal = withUsername(email).password("unused").roles("DEVELOPER").build();
        when(authentication.isAuthenticated()).thenReturn(true);
        when(authentication.getPrincipal()).thenReturn(principal);
        when(authentication.getName()).thenReturn(email);
        return authentication;
    }
}
