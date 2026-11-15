package com.cnpm.backend.security;

import java.util.Set;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Component;

import com.cnpm.backend.repository.UserRepository;

@Component
public class SystemAdminAccess {
    private static final Set<String> ADMIN_ROLES =
            Set.of("ADMIN", "ADMINISTRATOR", "ROLE_ADMIN", "ROLE_ADMINISTRATOR");
    private final UserRepository users;

    public SystemAdminAccess(UserRepository users) {
        this.users = users;
    }

    public boolean allows(Authentication authentication) {
        if (authentication.getPrincipal() instanceof OAuth2User oauth) {
            Object githubId = oauth.getAttribute("id");
            return githubId != null && users.findByGithubId(githubId.toString())
                    .filter(user -> user.isActive() && ADMIN_ROLES.contains(user.getRole())).isPresent();
        }
        return users.findByEmail(authentication.getName())
                .filter(user -> user.isActive() && ADMIN_ROLES.contains(user.getRole())).isPresent();
    }
}
