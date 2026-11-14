package com.cnpm.backend.security;

import java.io.IOException;
import java.util.Optional;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@Component
public class AccountStatusFilter extends OncePerRequestFilter {

    private final UserRepository userRepository;

    public AccountStatusFilter(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            filterChain.doFilter(request, response);
            return;
        }

        Optional<User> account = Optional.empty();
        if (authentication.getPrincipal() instanceof OAuth2User oauth2User) {
            Object githubId = oauth2User.getAttribute("id");
            if (githubId != null) {
                account = userRepository.findByGithubId(String.valueOf(githubId));
            }
        } else {
            account = userRepository.findByEmail(authentication.getName());
        }

        if (account.isEmpty() || !account.get().isActive()) {
            SecurityContextHolder.clearContext();
            if (request.getSession(false) != null) {
                request.getSession(false).invalidate();
            }
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "Account is disabled or unavailable");
            return;
        }

        filterChain.doFilter(request, response);
    }
}



