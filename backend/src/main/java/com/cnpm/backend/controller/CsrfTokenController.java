package com.cnpm.backend.controller;

import org.springframework.security.web.csrf.CsrfToken;
import jakarta.servlet.http.HttpServletRequest;
import com.cnpm.backend.config.SpaCsrfTokenRequestHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class CsrfTokenController {

    @GetMapping("/api/auth/csrf")
    public Map<String, String> csrfToken(HttpServletRequest request, CsrfToken csrfToken) {
        Object rawToken = request.getAttribute(SpaCsrfTokenRequestHandler.RAW_TOKEN_ATTRIBUTE);
        return Map.of("token", rawToken instanceof String value ? value : csrfToken.getToken());
    }
}
