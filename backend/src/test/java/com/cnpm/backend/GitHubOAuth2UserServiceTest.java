package com.cnpm.backend;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.service.GitHubOAuth2UserService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.Set;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class GitHubOAuth2UserServiceTest {

    @Test
    void activeGitHubUserReceivesPrimaryRoleAndInheritedPermissions() {
        assertOAuthAuthorities("DEVELOPER", "DOCUMENT_SUBMIT");
        assertOAuthAuthorities("STAFF", "DOCUMENT_REVIEW_QUEUE_VIEW");
        assertOAuthAuthorities("MANAGER", "DOCUMENT_APPROVAL_QUEUE_VIEW");
        assertOAuthAuthorities("TECHNICAL_LEAD", "DOCUMENT_TECHNICAL_REVIEW");
    }

    private void assertOAuthAuthorities(String roleName, String permissionCode) {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        server.expect(requestTo("https://api.github.test/user"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess("{\"id\":54321,\"login\":\"active-user\"}", MediaType.APPLICATION_JSON));

        UserRepository users = mock(UserRepository.class);
        RoleRepository roles = mock(RoleRepository.class);
        User activeUser = new User("active@example.test", "encoded", "Active", "User", roleName, true);
        activeUser.setGithubId("54321");
        when(users.findByGithubId("54321")).thenReturn(Optional.of(activeUser));
        Role role = new Role(roleName, roleName);
        role.getPermissions().add(new Permission(permissionCode, permissionCode));
        when(roles.findWithPermissionsByName(roleName)).thenReturn(Optional.of(role));

        GitHubOAuth2UserService service = new GitHubOAuth2UserService(users,
                new org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder(), roles);
        service.setRestOperations(restTemplate);
        var principal = service.loadUser(oauthRequest());

        assertThat(principal.getAuthorities()).extracting("authority")
                .contains("ROLE_" + roleName, permissionCode);
        server.verify();
    }

    @Test
    void rejectsGitHubLoginWhenLinkedAccountIsDisabled() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        server.expect(requestTo("https://api.github.test/user"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"id\":12345,\"login\":\"disabled-user\",\"name\":\"Disabled User\"}",
                        MediaType.APPLICATION_JSON));

        UserRepository repository = mock(UserRepository.class);
        User disabledUser = new User("disabled@example.test", "encoded",
                "Disabled", "User", "DEVELOPER", true);
        disabledUser.setGithubId("12345");
        disabledUser.setActive(false);
        when(repository.findByGithubId("12345")).thenReturn(Optional.of(disabledUser));

        GitHubOAuth2UserService service =
                new GitHubOAuth2UserService(repository, new org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder());
        service.setRestOperations(restTemplate);

        OAuth2UserRequest request = oauthRequest();

        assertThatThrownBy(() -> service.loadUser(request))
                .isInstanceOf(OAuth2AuthenticationException.class)
                .hasMessageContaining("This account has been disabled");

        server.verify();
    }

    private static OAuth2UserRequest oauthRequest() {
        ClientRegistration registration = ClientRegistration.withRegistrationId("github")
                .clientId("test-client")
                .clientSecret("test-secret")
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri("https://github.test/login/oauth/authorize")
                .tokenUri("https://github.test/login/oauth/access_token")
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("read:user")
                .userInfoUri("https://api.github.test/user")
                .userNameAttributeName("id")
                .clientName("GitHub")
                .build();
        OAuth2AccessToken token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-access-token",
                Instant.now(),
                Instant.now().plusSeconds(300),
                Set.of("read:user"));
        return new OAuth2UserRequest(registration, token);
    }
}
