package com.livingdocs.github.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** Requires the Backend service credential before accepting an identity header. */
@Component
public class InternalServiceAuthenticationFilter extends OncePerRequestFilter {

    private static final String CALLBACK_PATH = "/api/github/callback";
    private static final String HEALTH_PATH = "/actuator/health";
    private final String expectedCredential;

    public InternalServiceAuthenticationFilter(
            @Value("${security.internal-api-secret:}") String expectedCredential) {
        this.expectedCredential = expectedCredential == null ? "" : expectedCredential;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI().substring(request.getContextPath().length());
        return HEALTH_PATH.equals(path)
                || (CALLBACK_PATH.equals(path) && "GET".equals(request.getMethod()));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        String supplied = bearerCredential(request.getHeader(HttpHeaders.AUTHORIZATION));
        if (expectedCredential.isBlank() || supplied == null
                || !MessageDigest.isEqual(expectedCredential.getBytes(StandardCharsets.UTF_8),
                        supplied.getBytes(StandardCharsets.UTF_8))) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write("{\"code\":\"INTERNAL_SERVICE_AUTH_REQUIRED\","
                    + "\"message\":\"A trusted internal service credential is required.\"}");
            return;
        }
        filterChain.doFilter(request, response);
    }

    private String bearerCredential(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) return null;
        return authorization.substring("Bearer ".length());
    }
}
