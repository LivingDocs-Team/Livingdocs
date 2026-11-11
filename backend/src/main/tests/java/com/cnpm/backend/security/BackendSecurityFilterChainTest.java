package com.cnpm.backend.security;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.auth.CustomUserDetailsService;
import com.cnpm.backend.auth.GitHubOAuth2UserService;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.client.RestClient;

import java.util.Optional;
import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.core.userdetails.User.withUsername;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.util.UriUtils;

import java.nio.charset.StandardCharsets;
@WebMvcTest(controllers = {
        com.cnpm.backend.controller.GitHubIntegrationBffController.class,
        com.cnpm.backend.security.CsrfTokenController.class,
        com.cnpm.backend.auth.CurrentUserController.class,
        com.cnpm.backend.auth.OAuth2SuccessController.class,
        com.cnpm.backend.auth.UserLoginController.class,
        com.cnpm.backend.controller.AdminUserController.class,
        com.cnpm.backend.controller.AdminRoleController.class
}, properties = {
        "services.github-integration.base-url=http://127.0.0.1:1",
        "services.github-integration.internal-secret=filter-chain-test-credential",
        "spring.security.oauth2.client.registration.github.client-id=test-client",
        "spring.security.oauth2.client.registration.github.client-secret=test-secret",
        "SESSION_COOKIE_SECURE=false",
        "SESSION_COOKIE_SAME_SITE=Lax"
})
@Import({SecurityConfig.class, AccountStatusFilter.class, SpaCsrfTokenRequestHandler.class,
        BackendSecurityFilterChainTest.TestBeans.class})
class BackendSecurityFilterChainTest {

    private static final String EMAIL = "bff-user@example.test";
    private static final String PASSWORD = "test-only-password";

    @Autowired
    private MockMvc mvc;

    @Autowired
    private CustomUserDetailsService userDetailsService;

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private RoleRepository roleRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> tokenClient;

    @Autowired
    private GitHubOAuth2UserService gitHubUserService;

    private User testUser;

    @BeforeEach
    void setUp() {
        reset(tokenClient);
        UserDetails details = withUsername(EMAIL)
                .password(passwordEncoder.encode(PASSWORD))
                .roles("DEVELOPER")
                .build();
        when(userDetailsService.loadUserByUsername(EMAIL)).thenReturn(details);

        testUser = new User(EMAIL, "test-encoded-password", "Bff", "User", "DEVELOPER", true);
        testUser.setUsername("bff-user");
        ReflectionTestUtils.setField(testUser, "id", 73L);
        when(userRepository.findByEmail(EMAIL)).thenReturn(Optional.of(testUser));
    }

    @Test
    void githubCallbackRestoresCurrentUserFromSession() throws Exception {
        when(tokenClient.getTokenResponse(any())).thenReturn(OAuth2AccessTokenResponse
                .withToken("test-access-token")
                .tokenType(OAuth2AccessToken.TokenType.BEARER)
                .build());
        when(gitHubUserService.loadUser(any())).thenAnswer(invocation -> {
            OAuth2UserRequest request = invocation.getArgument(0);
            assertThat(request.getAccessToken().getTokenValue()).isEqualTo("test-access-token");
            return new DefaultOAuth2User(List.of(new SimpleGrantedAuthority("ROLE_DEVELOPER")),
                    Map.of("id", 12345), "id");
        });
        when(userRepository.findByGithubId("12345")).thenReturn(Optional.of(testUser));

        MockHttpSession session = githubCallback("/api/auth/oauth2/success");
        mvc.perform(get("/api/auth/oauth2/success").session(session))
                .andExpect(redirectedUrl("/?oauth=success"));
        mvc.perform(get("/api/auth/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(73))
                .andExpect(jsonPath("$.email").value(EMAIL))
                .andExpect(jsonPath("$.accessToken").doesNotExist());

        testUser.setActive(false);
        mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isUnauthorized());
        assertThat(session.isInvalid()).isTrue();
    }

    @Test
    void githubTokenRejectionDoesNotEstablishSession() throws Exception {
        when(tokenClient.getTokenResponse(any()))
                .thenThrow(new OAuth2AuthorizationException(new OAuth2Error("invalid_grant")));

        MockHttpSession session = githubCallback("/?oauth=error");
        verify(tokenClient).getTokenResponse(any());
        mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isUnauthorized());
    }

    private MockHttpSession githubCallback(String expectedRedirect) throws Exception {
        MvcResult start = mvc.perform(get("/oauth2/authorization/github"))
                .andExpect(status().is3xxRedirection())
                .andReturn();
        MockHttpSession session = (MockHttpSession) start.getRequest().getSession(false);
        String state = UriComponentsBuilder.fromUriString(start.getResponse().getRedirectedUrl())
                .build().getQueryParams().getFirst("state");
        assertThat(state).isNotBlank();
        mvc.perform(get("/login/oauth2/code/github").session(session)
                        .param("code", "test-code").param("state", UriUtils.decode(state, StandardCharsets.UTF_8)))
                .andExpect(redirectedUrl(expectedRedirect));
        return session;
    }

    @Test
    void missingOrExpiredSessionCannotCallBffEvenWithForgedIdentity() throws Exception {
        mvc.perform(get("/api/github/connection")
                        .header("X-User-Id", "forged-user"))
                .andExpect(status().isUnauthorized());

        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);
        String expiredSessionId = session.getId();
        session.invalidate();
        mvc.perform(get("/api/github/connection")
                        .cookie(new Cookie("JSESSIONID", expiredSessionId))
                        .header("X-User-Id", "forged-user"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void missingAndWrongCsrfAreRejectedButValidCsrfReachesAuthenticatedBff() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);
        clearInvocations(userRepository);

        mvc.perform(post("/api/workspaces/ws-73/repositories").session(session))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/workspaces/ws-73/repositories")
                        .session(session)
                        .cookie(csrf.cookie())
                        .header("X-XSRF-TOKEN", "wrong-token"))
                .andExpect(status().isForbidden());

        mvc.perform(post("/api/workspaces/ws-73/repositories")
                        .session(session)
                        .cookie(csrf.cookie())
                        .header("X-XSRF-TOKEN", csrf.token())
                        .header("X-User-Id", "forged-user")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"githubRepoIds\":[]}"))
                .andExpect(status().isBadGateway());

        verify(userRepository, atLeastOnce()).findByEmail(EMAIL);
    }

    @Test
    void logoutInvalidatesSessionAndSubsequentBffRequestIsUnauthorized() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);
        String sessionId = session.getId();

        mvc.perform(post("/api/auth/logout")
                        .session(session)
                        .cookie(csrf.cookie())
                        .header("X-XSRF-TOKEN", csrf.token()))
                .andExpect(status().isOk());

        assertThat(session.isInvalid()).isTrue();
        mvc.perform(get("/api/github/connection")
                        .cookie(new Cookie("JSESSIONID", sessionId)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void developerCannotAccessAdminUserManagementApi() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);

        mvc.perform(get("/api/admin/users").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void administratorAndLegacyAdminNeedBothAdminRoleAndPermissionAuthority() throws Exception {
        Csrf csrf = fetchCsrf();
        when(roleRepository.findAll()).thenReturn(java.util.List.of());

        MockHttpSession administrator = loginWithAuthorities(csrf, "ROLE_ADMINISTRATOR", "ROLE_VIEW");
        mvc.perform(get("/api/admin/roles").session(administrator)).andExpect(status().isOk());

        MockHttpSession legacyAdmin = loginWithAuthorities(csrf, "ROLE_ADMIN", "ROLE_VIEW");
        mvc.perform(get("/api/admin/roles").session(legacyAdmin)).andExpect(status().isOk());

        MockHttpSession missingPermission = loginWithAuthorities(csrf, "ROLE_ADMIN");
        mvc.perform(get("/api/admin/roles").session(missingPermission)).andExpect(status().isForbidden());
    }

    @Test
    void staffAndManagerPermissionsDoNotGrantSystemAdministration() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession staff = loginWithAuthorities(csrf, "ROLE_STAFF", "DOCUMENT_REVIEW_QUEUE_VIEW");
        mvc.perform(get("/api/admin/roles").session(staff)).andExpect(status().isForbidden());

        MockHttpSession manager = loginWithAuthorities(csrf, "ROLE_MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW");
        mvc.perform(get("/api/admin/roles").session(manager)).andExpect(status().isForbidden());
    }

    @Test
    void disabledAccountSessionIsRejectedAndInvalidatedOnNextRequest() throws Exception {
        Csrf csrf = fetchCsrf();
        MockHttpSession session = login(csrf);
        testUser.setActive(false);

        mvc.perform(get("/api/github/connection").session(session))
                .andExpect(status().isUnauthorized());

        assertThat(session.isInvalid()).isTrue();
    }

    @Test
    void csrfCookieUsesLocalHttpCompatibleFlags() throws Exception {
        Csrf csrf = fetchCsrf();
        assertThat(csrf.cookie()).isNotNull();
        assertThat(csrf.token()).isEqualTo(csrf.cookie().getValue());
        assertThat(csrf.cookie().getAttribute("SameSite")).isEqualTo("Lax");
        assertThat(csrf.cookie().getSecure()).isFalse();
        assertThat(csrf.cookie().isHttpOnly()).isTrue();
    }

    @Test
    void csrfCookieCanUseSecureAndSameSiteNoneBehindHttps() {
        var repository = new SecurityConfig().csrfTokenRepository(true, "None");
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        repository.saveToken(repository.generateToken(request), request, response);

        Cookie cookie = response.getCookie("XSRF-TOKEN");
        assertThat(cookie.getSecure()).isTrue();
        assertThat(cookie.getAttribute("SameSite")).isEqualTo("None");
    }

    private Csrf fetchCsrf() throws Exception {
        MvcResult result = mvc.perform(get("/api/auth/csrf"))
                .andExpect(status().isOk())
                .andReturn();
        String json = result.getResponse().getContentAsString();
        java.util.regex.Matcher matcher = java.util.regex.Pattern
                .compile("\\\"token\\\":\\\"([^\\\"]+)\\\"")
                .matcher(json);
        assertThat(matcher.find()).isTrue();
        String token = matcher.group(1);
        Cookie cookie = result.getResponse().getCookie("XSRF-TOKEN");
        return new Csrf(token, cookie);
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

    private MockHttpSession loginWithAuthorities(Csrf csrf, String... authorities) throws Exception {
        UserDetails details = withUsername(EMAIL)
                .password(passwordEncoder.encode(PASSWORD))
                .authorities(authorities)
                .build();
        when(userDetailsService.loadUserByUsername(EMAIL)).thenReturn(details);
        return login(csrf);
    }

    private record Csrf(String token, Cookie cookie) {
    }

    @TestConfiguration
    static class TestBeans {
        @Bean
        @SuppressWarnings("unchecked")
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> testTokenClient() {
            return mock(OAuth2AccessTokenResponseClient.class);
        }

        @Bean
        @Primary
        CustomUserDetailsService testUserDetailsService() {
            return mock(CustomUserDetailsService.class);
        }

        @Bean
        @Primary
        UserRepository testUserRepository() {
            return mock(UserRepository.class);
        }

        @Bean
        @Primary
        RoleRepository testRoleRepository() {
            return mock(RoleRepository.class);
        }

        @Bean
        @Primary
        PermissionRepository testPermissionRepository() {
            return mock(PermissionRepository.class);
        }

        @Bean
        @Primary
        GitHubOAuth2UserService testGitHubOAuth2UserService() {
            return mock(GitHubOAuth2UserService.class);
        }

        @Bean
        @Primary
        RestClient.Builder testRestClientBuilder() {
            return RestClient.builder();
        }
    }
}
