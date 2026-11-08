package com.cnpm.backend;

import com.cnpm.backend.controller.GitHubIntegrationBffController;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.entity.Permission;
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
    void workflowAuthorityHeaderIsRebuiltFromCurrentDatabaseRoleAndPermissions() throws Exception {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        UserRepository users = mock(UserRepository.class);
        RoleRepository roles = mock(RoleRepository.class);
        User authenticatedUser = mock(User.class);
        when(authenticatedUser.getId()).thenReturn(73L);
        when(authenticatedUser.getRole()).thenReturn("DEVELOPER");
        when(users.findByEmail("verified@example.test")).thenReturn(Optional.of(authenticatedUser));
        Role currentRole = new Role("DEVELOPER", "Developer");
        currentRole.getPermissions().add(new Permission("DOCUMENT_CREATE", "Create docs"));
        when(roles.findWithPermissionsByName("DEVELOPER")).thenReturn(Optional.of(currentRole));

        server.expect(requestTo("http://github.test:8082/api/document-workflows/mine"))
                .andExpect(header("X-User-Id", "73"))
                .andExpect(header("X-User-Authorities", "ROLE_DEVELOPER,DOCUMENT_CREATE"))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        GitHubIntegrationBffController controller = new GitHubIntegrationBffController(builder.build(), users,
                roles, "http://github.test:8082", "internal-test-credential");
        MockHttpServletRequest incoming = new MockHttpServletRequest(HttpMethod.GET.name(),
                "/api/document-workflows/mine");
        incoming.addHeader("X-User-Id", "forged-user");
        incoming.addHeader("X-User-Authorities", "ROLE_ADMIN,DOCUMENT_APPROVE");
        controller.proxy(incoming, authenticatedEmail("verified@example.test"), null);
        server.verify();
    }

    @Test
    void administratorReassignSendsOnlyBackendVerifiedActiveStaffTarget() throws Exception {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        UserRepository users = mock(UserRepository.class);
        RoleRepository roles = mock(RoleRepository.class);
        User admin = mock(User.class);
        when(admin.getId()).thenReturn(73L);
        when(admin.getRole()).thenReturn("ADMIN");
        when(users.findByEmail("verified@example.test")).thenReturn(Optional.of(admin));

        User staff = mock(User.class);
        when(staff.isActive()).thenReturn(true);
        when(staff.getRole()).thenReturn("STAFF");
        when(users.findById(81L)).thenReturn(Optional.of(staff));
        Role adminRole = new Role("ADMIN", "Legacy administrator");
        adminRole.getPermissions().add(new Permission("DOCUMENT_REASSIGN", "Reassign"));
        Role staffRole = new Role("STAFF", "Staff member");
        staffRole.getPermissions().add(new Permission("DOCUMENT_CLAIM", "Claim"));
        staffRole.getPermissions().add(new Permission("DOCUMENT_REVIEW", "Review"));
        when(roles.findWithPermissionsByName("ADMIN")).thenReturn(Optional.of(adminRole));
        when(roles.findWithPermissionsByName("STAFF")).thenReturn(Optional.of(staffRole));

        server.expect(requestTo("http://github.test:8082/api/document-workflows/11111111-1111-1111-1111-111111111111/reassign"))
                .andExpect(header("X-User-Id", "73"))
                .andExpect(header("X-User-Authorities", "ROLE_ADMIN,DOCUMENT_REASSIGN"))
                .andExpect(header("X-Verified-Staff-User-Id", "81"))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        var controller = new GitHubIntegrationBffController(builder.build(), users, roles,
                "http://github.test:8082", "internal-test-credential");
        MockHttpServletRequest incoming = new MockHttpServletRequest(HttpMethod.POST.name(),
                "/api/document-workflows/11111111-1111-1111-1111-111111111111/reassign");
        incoming.addHeader("X-Verified-Staff-User-Id", "999");
        controller.proxy(incoming, authenticatedEmail("verified@example.test"),
                "{\"targetStaffUserId\":81,\"reason\":\"Workload transfer\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        server.verify();
    }

    @Test
    void reassignRejectsInactiveTargetAndNonAdministratorBeforeProxying() {
        RestClient.Builder builder = RestClient.builder();
        UserRepository users = mock(UserRepository.class);
        RoleRepository roles = mock(RoleRepository.class);
        User admin = mock(User.class);
        when(admin.getId()).thenReturn(73L);
        when(admin.getRole()).thenReturn("ADMINISTRATOR");
        when(users.findByEmail("verified@example.test")).thenReturn(Optional.of(admin));
        User inactive = mock(User.class);
        when(inactive.isActive()).thenReturn(false);
        when(inactive.getRole()).thenReturn("STAFF");
        when(users.findById(81L)).thenReturn(Optional.of(inactive));
        Role administratorRole = new Role("ADMINISTRATOR", "Administrator");
        administratorRole.getPermissions().add(new Permission("DOCUMENT_REASSIGN", "Reassign"));
        when(roles.findWithPermissionsByName("ADMINISTRATOR")).thenReturn(Optional.of(administratorRole));
        when(roles.findWithPermissionsByName("STAFF")).thenReturn(Optional.of(new Role("STAFF", "Staff")));

        var controller = new GitHubIntegrationBffController(builder.build(), users, roles,
                "http://github.test:8082", "internal-test-credential");
        MockHttpServletRequest request = new MockHttpServletRequest(HttpMethod.POST.name(),
                "/api/document-workflows/11111111-1111-1111-1111-111111111111/reassign");
        byte[] body = "{\"targetStaffUserId\":81,\"reason\":\"Workload transfer\"}"
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);

        assertThatThrownBy(() -> controller.proxy(request, authenticatedEmail("verified@example.test"), body))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode().value()).isEqualTo(400));

        when(inactive.isActive()).thenReturn(true);
        when(inactive.getRole()).thenReturn("MANAGER");
        assertThatThrownBy(() -> controller.proxy(request, authenticatedEmail("verified@example.test"), body))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode().value()).isEqualTo(400));

        User manager = mock(User.class);
        when(manager.getId()).thenReturn(74L);
        when(manager.getRole()).thenReturn("MANAGER");
        when(users.findByEmail("manager@example.test")).thenReturn(Optional.of(manager));
        Role managerRole = new Role("MANAGER", "Manager");
        managerRole.getPermissions().add(new Permission("DOCUMENT_REASSIGN", "Reassign"));
        when(roles.findWithPermissionsByName("MANAGER")).thenReturn(Optional.of(managerRole));
        assertThatThrownBy(() -> controller.proxy(request, authenticatedEmail("manager@example.test"), body))
                .isInstanceOfSatisfying(ResponseStatusException.class,
                        e -> assertThat(e.getStatusCode().value()).isEqualTo(403));
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
