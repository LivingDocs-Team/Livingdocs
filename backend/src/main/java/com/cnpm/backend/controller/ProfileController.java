package com.cnpm.backend.controller;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

/**
 * LD-48: profile and notification preferences of the signed-in user.
 * LD-49 view the profile, LD-50 update it, LD-51 notification preferences.
 * Email is the sign-in name, so it is not changed here (administrators use /api/admin/users);
 * role and password are not part of the requests, so they cannot be changed either.
 */
@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    private final UserRepository userRepository;

    public ProfileController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @GetMapping
    @Transactional(readOnly = true)
    public ResponseEntity<?> getProfile(Authentication authentication) {
        User user = currentUser(authentication);
        return user == null ? unauthorized() : ResponseEntity.ok(toProfile(user));
    }

    /** Fields left out (null) stay as they are. Nothing is saved when one field is invalid. */
    @PatchMapping
    @Transactional
    public ResponseEntity<?> updateProfile(@RequestBody(required = false) UpdateProfileRequest request,
                                           Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (request == null) {
            return error(HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Request body is required.");
        }
        String username = request.username() == null ? null : request.username().trim();
        if (username != null && (username.isEmpty() || username.length() > 50)) {
            return error(HttpStatus.BAD_REQUEST, "PROFILE_INVALID", "Username must contain 1 to 50 characters.");
        }
        String invalidName = invalidName(request.firstName(), "First name");
        if (invalidName == null) {
            invalidName = invalidName(request.lastName(), "Last name");
        }
        if (invalidName != null) {
            return error(HttpStatus.BAD_REQUEST, "PROFILE_INVALID", invalidName);
        }
        if (username != null && userRepository.existsByUsernameIgnoreCaseAndIdNot(username, user.getId())) {
            return error(HttpStatus.CONFLICT, "USERNAME_TAKEN", "Username is already in use.");
        }

        if (username != null) {
            user.setUsername(username);
        }
        if (request.firstName() != null) {
            user.setFirstName(request.firstName().trim());
        }
        if (request.lastName() != null) {
            user.setLastName(request.lastName().trim());
        }
        return ResponseEntity.ok(toProfile(userRepository.save(user)));
    }

    @GetMapping("/notification-preferences")
    @Transactional(readOnly = true)
    public ResponseEntity<?> getNotificationPreferences(Authentication authentication) {
        User user = currentUser(authentication);
        return user == null ? unauthorized() : ResponseEntity.ok(toPreferences(user));
    }

    /** Replaces all four preferences; each one is required. */
    @PutMapping("/notification-preferences")
    @Transactional
    public ResponseEntity<?> updateNotificationPreferences(
            @RequestBody(required = false) NotificationPreferences request, Authentication authentication) {
        User user = currentUser(authentication);
        if (user == null) {
            return unauthorized();
        }
        if (request == null || request.emailUpdates() == null || request.documentChanges() == null
                || request.reviewRequests() == null || request.systemNotifications() == null) {
            return error(HttpStatus.BAD_REQUEST, "PREFERENCES_INVALID",
                    "emailUpdates, documentChanges, reviewRequests and systemNotifications are required.");
        }
        user.setNotificationEnabled(request.emailUpdates());
        user.setNotifyDocumentChanges(request.documentChanges());
        user.setNotifyReviewRequests(request.reviewRequests());
        user.setNotifySystem(request.systemNotifications());
        return ResponseEntity.ok(toPreferences(userRepository.save(user)));
    }

    private User currentUser(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return null;
        }
        if (authentication.getPrincipal() instanceof OAuth2User oauth2User) {
            Object githubId = oauth2User.getAttribute("id");
            return githubId == null ? null
                    : userRepository.findByGithubId(String.valueOf(githubId)).orElse(null);
        }
        return userRepository.findByEmail(authentication.getName()).orElse(null);
    }

    private static String invalidName(String value, String label) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() || trimmed.length() > 100 ? label + " must contain 1 to 100 characters." : null;
    }

    private static ResponseEntity<?> unauthorized() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
    }

    private static ResponseEntity<?> error(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(Map.of("status", status.value(), "code", code, "message", message));
    }

    private static ProfileResponse toProfile(User user) {
        return new ProfileResponse(user.getId(), user.getUsername(), user.getEmail(),
                user.getFirstName(), user.getLastName(), user.getRole());
    }

    private static NotificationPreferences toPreferences(User user) {
        return new NotificationPreferences(user.isNotificationEnabled(), user.isNotifyDocumentChanges(),
                user.isNotifyReviewRequests(), user.isNotifySystem());
    }

    public record UpdateProfileRequest(String username, String firstName, String lastName) {
    }

    public record ProfileResponse(Long id, String username, String email, String firstName, String lastName,
                                  String role) {
    }

    public record NotificationPreferences(Boolean emailUpdates, Boolean documentChanges, Boolean reviewRequests,
                                          Boolean systemNotifications) {
    }
}
