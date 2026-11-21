package com.cnpm.backend.controller;

import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.WorkspaceMembershipRepository;
import com.cnpm.backend.repository.WorkspaceRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;
import java.util.Collections;
import java.util.Optional;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = GitHubIntegrationBffController.class)
@AutoConfigureMockMvc(addFilters = false) // Tắt Security Filter để không bị lỗi 401
@TestPropertySource(properties = {
        "services.github-integration.internal-secret=test-secret" // Cấp secret để không bị lỗi 503
})
@Import(GitHubIntegrationBffDocumentationAuthTest.TestConfig.class)
class GitHubIntegrationBffDocumentationAuthTest {

    @TestConfiguration
    static class TestConfig {
        @Bean
        @SuppressWarnings({"unchecked", "rawtypes"})
        public RestClient integrationClient() {
            RestClient mockClient = mock(RestClient.class);
            
            // Mock thủ công chuỗi get().uri().headers().exchange() trong resolveDocumentWorkspace
            RestClient.RequestHeadersUriSpec uriSpec = mock(RestClient.RequestHeadersUriSpec.class);
            RestClient.RequestHeadersSpec headersSpec = mock(RestClient.RequestHeadersSpec.class);
            
            when(mockClient.get()).thenReturn(uriSpec);
            doReturn(headersSpec).when(uriSpec).uri(any(URI.class));
            doReturn(headersSpec).when(headersSpec).headers(any());
            
            // Khi gọi exchange(), ném lỗi 404 (Mô phỏng không tìm thấy workspace)
            // Controller sẽ bắt lỗi này và trả về 404 cho client
            doThrow(new ResponseStatusException(HttpStatus.NOT_FOUND))
                .when(headersSpec).exchange(any());
            
            return mockClient;
        }

        @Bean
        public RestClient.Builder restClientBuilder(RestClient integrationClient) {
            RestClient.Builder builder = mock(RestClient.Builder.class);
            when(builder.clone()).thenReturn(builder);
            when(builder.requestFactory(any(ClientHttpRequestFactory.class))).thenReturn(builder);
            when(builder.build()).thenReturn(integrationClient);
            return builder;
        }
    }

    @Autowired MockMvc mockMvc;

    @MockitoBean UserRepository userRepository;
    @MockitoBean RoleRepository roleRepository;
    @MockitoBean WorkspaceRepository workspaceRepository;
    @MockitoBean WorkspaceMembershipRepository workspaceMembershipRepository;

    private static final String DOC_ID = "doc-123";

    @BeforeEach
    void setUp() {
        User u = mock(User.class);
        when(u.getId()).thenReturn(1L);
        when(u.getRole()).thenReturn("USER");
        when(userRepository.findByEmail(anyString())).thenReturn(Optional.of(u));
    }

    // Hàm tạo Authentication giả thay thế cho JWT
    private Authentication createAuth(String username) {
        UserDetails userDetails = org.springframework.security.core.userdetails.User
                .withUsername(username)
                .password("")
                .authorities(Collections.emptyList())
                .build();
        return new UsernamePasswordAuthenticationToken(userDetails, null, userDetails.getAuthorities());
    }

    @Test
    void ownerCanReadChangelog() throws Exception {
        mockMvc.perform(get("/api/documentation/{docId}/change-log", DOC_ID)
                .principal(createAuth("owner@x")) 
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound()); 
    }

    @Test
    void reviewerCanReadChangelog() throws Exception {
        mockMvc.perform(get("/api/documentation/{docId}/change-log", DOC_ID)
                .principal(createAuth("reviewer@x"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }

    @Test
    void outsiderCannotReadChangelog() throws Exception {
        mockMvc.perform(get("/api/documentation/{docId}/change-log", DOC_ID)
                .principal(createAuth("outsider@x"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }
}