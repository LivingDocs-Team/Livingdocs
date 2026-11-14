package com.cnpm.backend.controller;

import java.time.LocalDateTime;
import java.util.Map;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@RestController
@RequestMapping("/api/admin/users")
public class AdminUserController {

    private final UserRepository userRepository;

    public AdminUserController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('USER_VIEW')")
    @Transactional(readOnly = true)
    public UserPageResponse listUsers(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String search,
            @RequestParam(required = false) String role,
            @RequestParam(required = false) Boolean active) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Page must be non-negative and size must be between 1 and 100");
        }

        String normalizedSearch = normalizeFilter(search);
        String normalizedRole = role == null || role.isBlank() ? null : role.trim().toUpperCase(java.util.Locale.ROOT);
        Page<UserResponse> users = userRepository.searchForAdministration(
                        normalizedSearch, normalizedRole, active,
                        PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt")))
                .map(AdminUserController::toResponse);

        return new UserPageResponse(users.getContent(), users.getNumber(),
                users.getSize(), users.getTotalElements(), users.getTotalPages(),
                users.isFirst(), users.isLast());
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('USER_VIEW')")
    @Transactional(readOnly = true)
    public UserResponse getUser(@PathVariable Long id) {
        return toResponse(findUser(id));
    }

    @PatchMapping("/{id}")
    @PreAuthorize("hasAuthority('USER_UPDATE')")
    @Transactional
    public UserResponse updateUser(
            @PathVariable Long id,
            @RequestBody UpdateUserRequest request) {
        if (request == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Request body is required");
        }
        User user = findUser(id);

        if (request.username() != null) {
            String username = request.username().trim();
            if (username.isEmpty() || username.length() > 50) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "Username must contain 1 to 50 characters");
            }
            if (userRepository.existsByUsernameIgnoreCaseAndIdNot(username, id)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "Username is already in use");
            }
            user.setUsername(username);
        }

        if (request.email() != null) {
            String email = request.email().trim().toLowerCase();
            if (email.isEmpty() || email.length() > 255 || !email.matches("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$")) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "A valid email address is required");
            }
            if (userRepository.existsByEmailIgnoreCaseAndIdNot(email, id)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT,
                        "Email is already in use");
            }
            user.setEmail(email);
        }

        if (request.firstName() != null) {
            user.setFirstName(validateName(request.firstName(), "First name"));
        }
        if (request.lastName() != null) {
            user.setLastName(validateName(request.lastName(), "Last name"));
        }

        return toResponse(userRepository.save(user));
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAuthority('USER_DISABLE')")
    @Transactional
    public ResponseEntity<?> updateStatus(
            @PathVariable Long id,
            @RequestBody UpdateUserStatusRequest request,
            Authentication authentication) {
        if (request == null || request.active() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "The active field is required");
        }

        User actor = findAuthenticatedUser(authentication);
        if (actor.getId().equals(id)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Administrators cannot change their own account status");
        }

        User target = findUser(id);
        target.setActive(request.active());
        return ResponseEntity.ok(toResponse(userRepository.save(target)));
    }

    @PatchMapping("/{id}/role")
    @PreAuthorize("hasAuthority('USER_ASSIGN_ROLE')")
    @Transactional
    public UserResponse updatePrimaryRole(
            @PathVariable Long id,
            @RequestBody UpdateUserRoleRequest request,
            Authentication authentication) {
        if (request == null || request.role() == null || request.role().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The role field is required");
        }
        User actor = findAuthenticatedUser(authentication);
        if (actor.getId().equals(id)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Administrators cannot change their own role");
        }
        String role = request.role().trim().toUpperCase(java.util.Locale.ROOT);
        if (!java.util.Set.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR").contains(role)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unknown system role");
        }
        User target = findUser(id);
        target.setRole(role);
        return toResponse(userRepository.save(target));
    }

    private User findUser(Long id) {
        return userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "User not found"));
    }

    private User findAuthenticatedUser(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (authentication.getPrincipal() instanceof OAuth2User oauth2User) {
            Object githubId = oauth2User.getAttribute("id");
            if (githubId != null) {
                return userRepository.findByGithubId(String.valueOf(githubId))
                        .orElseThrow(() -> new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED));
            }
        }
        return userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.UNAUTHORIZED));
    }

    private static String normalizeFilter(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private static String validateName(String value, String label) {
        String normalized = value.trim();
        if (normalized.isEmpty() || normalized.length() > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    label + " must contain 1 to 100 characters");
        }
        return normalized;
    }

    private static UserResponse toResponse(User user) {
        return new UserResponse(user.getId(), user.getUsername(), user.getEmail(),
                user.getFirstName(), user.getLastName(), user.getRole(),
                user.isActive(), user.getCreatedAt());
    }

    public record UpdateUserRequest(
            String username,
            String email,
            String firstName,
            String lastName) {
    }

    public record UpdateUserStatusRequest(Boolean active) {
    }

    public record UpdateUserRoleRequest(String role) { }

    public record UserResponse(
            Long id,
            String username,
            String email,
            String firstName,
            String lastName,
            String role,
            boolean active,
            LocalDateTime createdAt) {
    }

    public record UserPageResponse(
            java.util.List<UserResponse> content,
            int page,
            int size,
            long totalElements,
            int totalPages,
            boolean first,
            boolean last) {
    }
}



