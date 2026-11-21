package com.cnpm.backend.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.security.core.userdetails.User.withUsername;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.client.RestClient;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.auth.CustomUserDetailsService;
import com.cnpm.backend.auth.GitHubOAuth2UserService;

import jakarta.servlet.http.Cookie;

/**
 * LD-403: the browser-facing 401 / CSRF behaviour of the document-workflow routes that the
 * Backend proxies to GitHub Integration, through the real SecurityConfig filter chain.
 */
@WebMvcTest(controllers = {
        com.cnpm.backend.controller.GitHubIntegrationBffController.class,
        com.cnpm.backend.security.CsrfTokenController.class,
        com.cnpm.backend.auth.UserLoginController.class
}, properties = {
        "services.github-integration.base-url=http://127.0.0.1:1",
        "services.github-integration.internal-secret=workflow-routes-test-credential",
        "spring.security.oauth2.client.registration.github.client-id=test-client",
        "spring.security.oauth2.client.registration.github.client-secret=test-secret",
        "SESSION_COOKIE_SECURE=false",
        "SESSION_COOKIE_SAME_SITE=Lax"
})
@Import({SecurityConfig.class, AccountStatusFilter.class, SpaCsrfTokenRequestHandler.class,
        DocumentWorkflowRoutesSecurityTest.TestBeans.class})
class DocumentWorkflowRoutesSecurityTest {

    private static final String EMAIL = "workflow-user@example.test";
    private static final String PASSWORD = "test-only-password";
    private static final String ID = "11111111-1111-4111-8111-111111111111";

    /** method, path, JSON body (null for GET). */
    private static final List<String[]> WORKFLOW_ROUTES = List.of(
            new String[] {"GET", "/api/document-workflows/mine", null},
            new String[] {"GET", "/api/document-workflows/staff/queue", null},
            new String[] {"GET", "/api/document-workflows/manager/queue", null},
            new String[] {"GET", "/api/document-workflows/history-accessible", null},
            new String[] {"GET", "/api/document-workflows/" + ID, null},
            new String[] {"GET", "/api/document-workflows/" + ID + "/history", null},
            new String[] {"POST", "/api/document-workflows", "{\"documentId\":\"doc-1\"}"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/submit", null},
            new String[] {"POST", "/api/document-workflows/" + ID + "/claim", null},
            new String[] {"POST", "/api/document-workflows/" + ID + "/staff-review", "{\"result\":\"PASSED\"}"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/approve", null},
            new String[] {"POST", "/api/document-workflows/" + ID + "/reject", "{\"comment\":\"no\"}"},
            new String[] {"POST", "/api/document-workflows/" + ID + "/rollback",
                    "{\"sourceVersion\":1,\"reason\":\"restore\"}"},
            new String[] {"PUT", "/api/document-workflows/" + ID + "/document", "{\"content\":\"# x\"}"});

    /** The first role of the matrix that may use the route (so the request passes the BFF's role check). */
    private static String roleAllowedFor(String[] route) {
        return ScreenPermissions.ROLES.stream()
                .filter(role -> ApiRoutePermissions.evaluate(route[0], route[1], role).allowed())
                .findFirst().orElseThrow();
    }

    @Autowired
    private MockMvc mvc;
    @Autowired
    private CustomUserDetailsService userDetailsService;
    @Autowired
    private UserRepository userRepository;
    @Autowired
    private PasswordEncoder passwordEncoder;

    @BeforeEach
    void setUp() {
        UserDetails details = withUsername(EMAIL).password(passwordEncoder.encode(PASSWORD))
                .roles("DEVELOPER").build();
        when(userDetailsService.loadUserByUsername(EMAIL)).thenReturn(details);
        User user = new User(EMAIL, "encoded", "Workflow", "User", "DEVELOPER", true);
        user.setUsername("workflow-user");
        ReflectionTestUtils.setField(user, "id", 73L);
        when(userRepository.findByEmail(EMAIL)).thenReturn(Optional.of(user));
    }

    @Test
    void unauthenticatedReadsOfEveryWorkflowRouteAreUnauthorizedEvenWithForgedIdentity() throws Exception {
        for (String[] route : WORKFLOW_ROUTES) {
            if (!"GET".equals(route[0])) continue;
            mvc.perform(get(route[1])
                            .header("X-User-Id", "92")
                            .header("X-User-Authorities", "ROLE_MANAGER,DOCUMENT_APPROVE"))
                    .andExpect(status().isUnauthorized());
        }
    }

    @Test
    void unauthenticatedWritesAreUnauthorizedWhenCsrfIsValidAndForbiddenWhenItIsMissing() throws Exception {
        Csrf csrf = fetchCsrf();
        for (String[] route : WORKFLOW_ROUTES) {
            if ("GET".equals(route[0])) continue;
            // No CSRF token: the CSRF filter answers first.
            mvc.perform(withBody(route)).andExpect(status().isForbidden());
            // Valid CSRF but no session: the request is not authenticated.
            mvc.perform(withBody(route).cookie(csrf.cookie()).header("X-XSRF-TOKEN", csrf.token())
                            .header("X-User-Id", "92"))
                    .andExpect(status().isUnauthorized());
        }
    }

    @Test
    void authenticatedWritesNeedAValidCsrfTokenAndThenReachTheBffProxy() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);

        for (String[] route : WORKFLOW_ROUTES) {
            if ("GET".equals(route[0])) continue;
            mvc.perform(withBody(route).session(session)).andExpect(status().isForbidden());
            mvc.perform(withBody(route).session(session).cookie(csrf.cookie())
                            .header("X-XSRF-TOKEN", "wrong-token"))
                    .andExpect(status().isForbidden());
            // The session and CSRF are accepted, so the BFF proxies to GitHub Integration; the test
            // base URL is unreachable, which the BFF reports as 502 (never 401/403). The BFF also applies the
            // Screen Authorization matrix, so the user acts as a role that may use this route.
            userRepository.findByEmail(EMAIL).orElseThrow().setRole(roleAllowedFor(route));
            mvc.perform(withBody(route).session(session).cookie(csrf.cookie())
                            .header("X-XSRF-TOKEN", csrf.token()))
                    .andExpect(status().isBadGateway());
        }
    }

    @Test
    void aValidSessionAndCsrfDoNotLetARoleUseAWorkflowRouteOfAnotherRole() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);   // a Developer
        for (String path : new String[] {"/approve", "/reject", "/claim", "/staff-review"}) {
            // CSRF is valid, so the 403 can only come from the role check (the proxy would answer 502).
            mvc.perform(post("/api/document-workflows/" + ID + path).session(session).cookie(csrf.cookie())
                            .header("X-XSRF-TOKEN", csrf.token())
                            .contentType(MediaType.APPLICATION_JSON).content("{}"))
                    .andExpect(status().isForbidden());
        }
        mvc.perform(get("/api/document-workflows/manager/queue").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void sessionEndedByLogoutCannotReadWorkflowRoutesAnyMore() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);
        mvc.perform(get("/api/document-workflows/mine").session(session))
                .andExpect(status().isBadGateway());   // authenticated: proxied (target unreachable)

        mvc.perform(post("/api/auth/logout").session(session).cookie(csrf.cookie())
                        .header("X-XSRF-TOKEN", csrf.token()))
                .andExpect(status().isOk());
        mvc.perform(get("/api/document-workflows/mine").session(session))
                .andExpect(status().isUnauthorized());
    }

    private static MockHttpServletRequestBuilder withBody(String[] route) {
        MockHttpServletRequestBuilder builder = switch (route[0]) {
            case "POST" -> post(route[1]);
            case "PUT" -> put(route[1]);
            default -> get(route[1]);
        };
        if (route[2] != null) {
            builder.contentType(MediaType.APPLICATION_JSON).content(route[2]);
        }
        return builder;
    }

    private Csrf fetchCsrf() throws Exception {
        MvcResult result = mvc.perform(get("/api/auth/csrf")).andExpect(status().isOk()).andReturn();
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("\"token\":\"([^\"]+)\"").matcher(result.getResponse().getContentAsString());
        assertThat(matcher.find()).isTrue();
        return new Csrf(matcher.group(1), result.getResponse().getCookie("XSRF-TOKEN"));
    }

    private MockHttpSession login(Csrf csrf) throws Exception {
        MvcResult result = mvc.perform(post("/api/auth/login")
                        .cookie(csrf.cookie())
                        .header("X-XSRF-TOKEN", csrf.token())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + EMAIL + "\",\"password\":\"" + PASSWORD + "\"}"))
                .andExpect(status().isOk())
                .andReturn();
        return (MockHttpSession) result.getRequest().getSession(false);
    }

    private record Csrf(String token, Cookie cookie) {
    }

    @TestConfiguration
    static class TestBeans {
        @Bean @Primary CustomUserDetailsService testUserDetailsService() { return mock(CustomUserDetailsService.class); }
        @Bean @Primary UserRepository testUserRepository() { return mock(UserRepository.class); }
        @Bean @Primary RoleRepository testRoleRepository() { return mock(RoleRepository.class); }
        @Bean @Primary PermissionRepository testPermissionRepository() { return mock(PermissionRepository.class); }
        @Bean @Primary GitHubOAuth2UserService testGitHubOAuth2UserService() { return mock(GitHubOAuth2UserService.class); }
        @Bean @Primary RestClient.Builder testRestClientBuilder() { return RestClient.builder(); }
    }
}
