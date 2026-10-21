package com.cnpm.backend;

import com.cnpm.backend.controller.GitHubIntegrationBffController;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.util.Optional;
import java.net.SocketTimeoutException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;

class GitHubIntegrationBffControllerTest {

    @Test
    void replacesBrowserIdentityWithUserResolvedFromAuthenticatedPrincipal() throws Exception {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        UserRepository users = mock(UserRepository.class);
        User authenticatedUser = mock(User.class);
        when(authenticatedUser.getId()).thenReturn(73L);
        when(users.findByEmail("verified@example.test")).thenReturn(Optional.of(authenticatedUser));
        Authentication authentication = authenticatedEmail("verified@example.test");

        server.expect(requestTo("http://github.test:8082/api/github/connection?view=full"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer internal-test-credential"))
                .andExpect(header("X-User-Id", "73"))
                .andRespond(withSuccess("{\"connected\":true}", MediaType.APPLICATION_JSON));

        GitHubIntegrationBffController controller = controller(builder, users, "internal-test-credential");
        MockMvc mvc = MockMvcBuilders.standaloneSetup(controller).build();
        var response = mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .get("/api/github/connection?view=full")
                        .principal(authentication)
                        .header("X-User-Id", "forged-user")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer forged-credential"))
                .andReturn().getResponse();

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(response.getContentAsString()).contains("connected");
        server.verify();
    }

    @Test
    void rejectsRequestWithoutAuthenticatedPrincipal() {
        GitHubIntegrationBffController controller = controller(RestClient.builder(), mock(UserRepository.class),
                "internal-test-credential");
        MockHttpServletRequest incoming = new MockHttpServletRequest(HttpMethod.GET.name(), "/api/github/connection");
        incoming.addHeader("X-User-Id", "forged-user");

        assertThatThrownBy(() -> controller.proxy(incoming, null, null))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        exception -> assertThat(exception.getStatusCode().value()).isEqualTo(401));
    }

    @Test
    void mapsDownstreamTimeoutToGenericBadGateway() throws Exception {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        UserRepository users = mock(UserRepository.class);
        User authenticatedUser = mock(User.class);
        when(authenticatedUser.getId()).thenReturn(73L);
        when(users.findByEmail("verified@example.test")).thenReturn(Optional.of(authenticatedUser));
        server.expect(requestTo("http://github.test:8082/api/github/connection"))
                .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer internal-test-credential"))
                .andRespond(withException(new SocketTimeoutException("upstream-diagnostic-marker")));

        GitHubIntegrationBffController controller = controller(builder, users, "internal-test-credential");
        MockHttpServletRequest incoming = new MockHttpServletRequest(HttpMethod.GET.name(),
                "/api/github/connection");

        assertThatThrownBy(() -> controller.proxy(incoming,
                authenticatedEmail("verified@example.test"), null))
                .isInstanceOfSatisfying(ResponseStatusException.class, exception -> {
                    assertThat(exception.getStatusCode().value()).isEqualTo(502);
                    assertThat(exception.getReason()).doesNotContain("upstream-diagnostic-marker");
                });
        server.verify();
    }

    private GitHubIntegrationBffController controller(RestClient.Builder builder,
            UserRepository users, String secret) {
        return new GitHubIntegrationBffController(builder.build(), users, "http://github.test:8082", secret);
    }

    private Authentication authenticatedEmail(String email) {
        UserDetails principal = mock(UserDetails.class);
        when(principal.getUsername()).thenReturn(email);
        Authentication authentication = mock(Authentication.class);
        when(authentication.isAuthenticated()).thenReturn(true);
        when(authentication.getPrincipal()).thenReturn(principal);
        return authentication;
    }
}
