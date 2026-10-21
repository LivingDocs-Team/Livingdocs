package com.cnpm.backend;

import com.cnpm.backend.config.SecurityConfig;
import com.cnpm.backend.config.SpaCsrfTokenRequestHandler;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.CustomUserDetailsService;
import com.cnpm.backend.service.GitHubOAuth2UserService;
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

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.core.userdetails.User.withUsername;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {
        com.cnpm.backend.controller.GitHubIntegrationBffController.class,
        com.cnpm.backend.controller.CsrfTokenController.class,
        com.cnpm.backend.controller.UserLoginController.class
}, properties = {
        "services.github-integration.base-url=http://127.0.0.1:1",
        "services.github-integration.internal-secret=filter-chain-test-credential",
        "SESSION_COOKIE_SECURE=false",
        "SESSION_COOKIE_SAME_SITE=Lax"
})
@Import({SecurityConfig.class, SpaCsrfTokenRequestHandler.class,
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
    private PasswordEncoder passwordEncoder;

    @BeforeEach
    void setUp() {
        UserDetails details = withUsername(EMAIL)
                .password(passwordEncoder.encode(PASSWORD))
                .roles("DEVELOPER")
                .build();
        when(userDetailsService.loadUserByUsername(EMAIL)).thenReturn(details);

        User user = new User(EMAIL, "test-encoded-password", "Bff", "User", "DEVELOPER", true);
        user.setUsername("bff-user");
        ReflectionTestUtils.setField(user, "id", 73L);
        when(userRepository.findByEmail(EMAIL)).thenReturn(Optional.of(user));
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

        verify(userRepository).findByEmail(EMAIL);
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

    private record Csrf(String token, Cookie cookie) {
    }

    @TestConfiguration
    static class TestBeans {
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
