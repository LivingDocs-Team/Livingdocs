
package com.cnpm.backend.service;

import java.util.Map;
import java.util.UUID;

import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

@Service
public class GitHubOAuth2UserService extends DefaultOAuth2UserService {

    private final UserRepository userRepository;
private final PasswordEncoder passwordEncoder;

public GitHubOAuth2UserService(
        UserRepository userRepository,
        PasswordEncoder passwordEncoder) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
}

    @Override
    @Transactional
    public OAuth2User loadUser(OAuth2UserRequest request)
            throws OAuth2AuthenticationException {

        OAuth2User githubUser = super.loadUser(request);

        Map<String, Object> attributes = githubUser.getAttributes();
        Object idAttribute = attributes.get("id");

        if (idAttribute == null) {
            throw new AuthenticationServiceException(
                    "GitHub account ID is missing");
        }

        String githubId = String.valueOf(idAttribute);

        User user = userRepository.findByGithubId(githubId)
                .orElseGet(() -> createGitHubUser(attributes, githubId));

        return new org.springframework.security.oauth2.core.user.DefaultOAuth2User(
                githubUser.getAuthorities(),
                attributes,
                "id");
    }

    private User createGitHubUser(
            Map<String, Object> attributes,
            String githubId) {

        String githubLogin = stringValue(attributes.get("login"));
        String name = stringValue(attributes.get("name"));

        if (githubLogin == null || githubLogin.isBlank()) {
            throw new AuthenticationServiceException(
                    "GitHub username is missing");
        }

String[] nameParts = (name == null || name.isBlank())
        ? new String[] { githubLogin, "GitHub" }
        : name.trim().split("\\s+", 2);

String firstName = nameParts[0];
String lastName = nameParts.length > 1
        && !nameParts[1].isBlank()
                ? nameParts[1]
                : "GitHub";

        String email = stringValue(attributes.get("email"));

        if (email == null || email.isBlank()) {
            email = "github-" + githubId + "@users.noreply.github.com";
        }

        if (userRepository.existsByEmail(email)) {
            throw new AuthenticationServiceException(
                    "This email already belongs to another account. "
                    + "Sign in with that account first.");
        }

        String username = uniqueUsername(githubLogin, githubId);

User newUser = new User(
        email,
        passwordEncoder.encode(UUID.randomUUID().toString()),
        firstName,
        lastName,
        "DEVELOPER",
        true);

        newUser.setUsername(username);
        newUser.setGithubId(githubId);

        return userRepository.save(newUser);
    }

    private String uniqueUsername(String login, String githubId) {
        String base = login.replaceAll("[^a-zA-Z0-9_]", "_");

        if (base.isBlank()) {
            base = "github";
        }

        base = base.substring(0, Math.min(base.length(), 35));

        String candidate = base;
        if (userRepository.existsByUsername(candidate)) {
            candidate = base + "_" + githubId;
            candidate = candidate.substring(
                    0, Math.min(candidate.length(), 50));
        }

        if (userRepository.existsByUsername(candidate)) {
            throw new AuthenticationServiceException(
                    "Could not generate a unique username");
        }

        return candidate;
    }

    private String stringValue(Object value) {
        return value == null ? null : value.toString().trim();
    }
}
