package com.cnpm.backend.controller;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@RestController
@RequestMapping("/api/auth")
public class CurrentUserController {

    private final UserRepository userRepository;

    public CurrentUserController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @GetMapping("/me")
    public ResponseEntity<?> currentUser(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        User user;

        if (authentication.getPrincipal() instanceof OAuth2User oauth2User) {
            Object githubId = oauth2User.getAttribute("id");

            if (githubId == null) {
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
            }

            user = userRepository.findByGithubId(String.valueOf(githubId))
                    .orElse(null);
        } else {
            user = userRepository.findByEmail(authentication.getName())
                    .orElse(null);
        }

        if (user == null) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        return ResponseEntity.ok(Map.of(
                "id", user.getId(),
                "email", user.getEmail(),
                "username", user.getUsername(),
                "firstName", user.getFirstName(),
                "lastName", user.getLastName(),
                "role", user.getRole()
        ));
    }
}