
package com.cnpm.backend.controller;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@RestController
public class OAuth2SuccessController {

    private final UserRepository userRepository;

    public OAuth2SuccessController(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @GetMapping("/api/auth/oauth2/success")
    public Map<String, Object> success(
            @AuthenticationPrincipal OAuth2User oauth2User) {

        Object githubIdAttribute = oauth2User.getAttribute("id");
        String githubId = String.valueOf(githubIdAttribute);

        User user = userRepository.findByGithubId(githubId)
                .orElseThrow(() ->
                        new IllegalStateException(
                                "GitHub account was not found"));

        return Map.of(
                "message", "GitHub login successful",
                "id", user.getId(),
                "email", user.getEmail(),
                "username", user.getUsername(),
                "firstName", user.getFirstName(),
                "lastName", user.getLastName(),
                "role", user.getRole()
        );
    }
}
