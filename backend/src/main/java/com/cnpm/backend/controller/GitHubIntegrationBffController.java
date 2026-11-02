package com.cnpm.backend.controller;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;
import java.time.Duration;
import java.util.List;

/** Proxies authenticated browser requests to GitHub Integration. */
@RestController
@RequestMapping(path = {
        "/api/github/**", "/api/workspaces/**", "/api/repositories/**", "/api/documentation/**"
}, method = {org.springframework.web.bind.annotation.RequestMethod.GET,
        org.springframework.web.bind.annotation.RequestMethod.POST,
        org.springframework.web.bind.annotation.RequestMethod.PUT,
        org.springframework.web.bind.annotation.RequestMethod.DELETE})
public class GitHubIntegrationBffController {

    private static final List<String> FORWARDED_RESPONSE_HEADERS = List.of("Retry-After");

    private final RestClient integrationClient;
    private final UserRepository userRepository;
    private final String integrationSecret;
    private final String integrationBaseUrl;

    @Autowired
    public GitHubIntegrationBffController(RestClient.Builder builder,
            UserRepository userRepository,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String integrationBaseUrl,
            @Value("${services.github-integration.internal-secret:}") String integrationSecret,
            @Value("${services.github-integration.connect-timeout:5s}") Duration connectTimeout,
            @Value("${services.github-integration.read-timeout:150s}") Duration readTimeout) {
        this(createIntegrationClient(builder, connectTimeout, readTimeout), userRepository,
                integrationBaseUrl, integrationSecret);
    }

    public GitHubIntegrationBffController(RestClient integrationClient, UserRepository userRepository,
            String integrationBaseUrl, String integrationSecret) {
        this.integrationClient = integrationClient;
        this.userRepository = userRepository;
        this.integrationBaseUrl = integrationBaseUrl.replaceAll("/+$", "");
        this.integrationSecret = integrationSecret == null ? "" : integrationSecret;
    }

    private static RestClient createIntegrationClient(RestClient.Builder builder,
            Duration connectTimeout, Duration readTimeout) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);
        return builder.clone().requestFactory(requestFactory).build();
    }

    @RequestMapping
    public ResponseEntity<byte[]> proxy(HttpServletRequest incoming,
            Authentication authentication,
            @RequestBody(required = false) byte[] body) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (integrationSecret.isBlank()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "GitHub Integration internal credential is not configured.");
        }

        User user = authenticatedUser(authentication);
        String path = incoming.getRequestURI().substring(incoming.getContextPath().length());
        String query = incoming.getQueryString();
        URI target = URI.create(integrationBaseUrl + path + (query == null ? "" : "?" + query));
        HttpMethod method = HttpMethod.valueOf(incoming.getMethod());
        var request = integrationClient.method(method).uri(target);
        request.headers(headers -> {
            headers.setBearerAuth(integrationSecret);
            headers.set("X-User-Id", user.getId().toString());
            String contentType = incoming.getContentType();
            if (contentType != null) headers.set(HttpHeaders.CONTENT_TYPE, contentType);
            String accept = incoming.getHeader(HttpHeaders.ACCEPT);
            if (accept != null) headers.set(HttpHeaders.ACCEPT, accept);
        });
        if (body != null && body.length > 0) request.body(body);

        try {
            return request.exchange((outgoing, response) -> {
                HttpHeaders headers = new HttpHeaders();
                MediaType contentType = response.getHeaders().getContentType();
                if (contentType != null) headers.setContentType(contentType);
                for (String name : FORWARDED_RESPONSE_HEADERS) {
                    String value = response.getHeaders().getFirst(name);
                    if (value != null) headers.set(name, value);
                }
                byte[] responseBody = response.getBody().readAllBytes();
                return ResponseEntity.status(response.getStatusCode()).headers(headers).body(responseBody);
            });
        } catch (org.springframework.web.client.RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "GitHub Integration is unavailable.");
        }
    }

    private User authenticatedUser(Authentication authentication) {
        if (authentication.getPrincipal() instanceof UserDetails details) {
            return userRepository.findByEmail(details.getUsername())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        }
        if (authentication.getPrincipal() instanceof OAuth2User oauthUser) {
            Object githubId = oauthUser.getAttribute("id");
            if (githubId != null) {
                return userRepository.findByGithubId(String.valueOf(githubId))
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
            }
        }
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
}
