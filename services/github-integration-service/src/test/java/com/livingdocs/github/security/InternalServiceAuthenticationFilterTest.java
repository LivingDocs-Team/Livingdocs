package com.livingdocs.github.security;

import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;

class InternalServiceAuthenticationFilterTest {

    private static final String TEST_CREDENTIAL = "test-only-internal-credential";

    @Test
    void rejectsMissingCredentialAndDoesNotContinue() throws Exception {
        assertRejected(null);
    }

    @Test
    void rejectsInvalidCredentialAndDoesNotContinue() throws Exception {
        assertRejected("Bearer invalid-test-credential");
    }

    @Test
    void rejectsAllApiRequestsWhenCredentialIsNotConfigured() throws Exception {
        InternalServiceAuthenticationFilter filter = new InternalServiceAuthenticationFilter("");
        MockHttpServletRequest request = apiRequest();
        request.addHeader("Authorization", "Bearer any-value");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(request, response, (req, res) -> continued.set(true));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(continued).isFalse();
    }

    @Test
    void acceptsCorrectServiceCredential() throws Exception {
        InternalServiceAuthenticationFilter filter = new InternalServiceAuthenticationFilter(TEST_CREDENTIAL);
        MockHttpServletRequest request = apiRequest();
        request.addHeader("Authorization", "Bearer " + TEST_CREDENTIAL);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(request, response, (req, res) -> continued.set(true));

        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(continued).isTrue();
    }

    @Test
    void allowsOneTimeStateCallbackWithoutServiceCredential() throws Exception {
        InternalServiceAuthenticationFilter filter = new InternalServiceAuthenticationFilter(TEST_CREDENTIAL);
        MockHttpServletRequest request = apiRequest();
        request.setRequestURI("/api/github/callback");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(request, response, (req, res) -> continued.set(true));

        assertThat(continued).isTrue();
    }

    private void assertRejected(String authorization) throws Exception {
        InternalServiceAuthenticationFilter filter = new InternalServiceAuthenticationFilter(TEST_CREDENTIAL);
        MockHttpServletRequest request = apiRequest();
        if (authorization != null) request.addHeader("Authorization", authorization);
        request.addHeader("X-User-Id", "forged-user");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(request, response, (req, res) -> continued.set(true));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("INTERNAL_SERVICE_AUTH_REQUIRED");
        assertThat(continued).isFalse();
    }

    private MockHttpServletRequest apiRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/github/connection");
        request.setServletPath("/api/github/connection");
        return request;
    }
}
