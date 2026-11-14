package com.cnpm.backend;

import com.cnpm.backend.controller.WorkspaceController;
import com.cnpm.backend.dto.WorkspaceRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.entity.Workspace;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.WorkspaceService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.Optional;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class WorkspaceControllerTest {

    private final WorkspaceService workspaces = mock(WorkspaceService.class);
    private final UserRepository users = mock(UserRepository.class);
    private MockMvc mvc;
    private User owner;
    private Authentication authentication;

    @BeforeEach
    void setUp() {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        mvc = MockMvcBuilders.standaloneSetup(new WorkspaceController(workspaces, users))
                .setValidator(validator).build();
        owner = new User("owner@example.test", "unused", "Owner", "Test", "DEVELOPER", true);
        ReflectionTestUtils.setField(owner, "id", 73L);
        authentication = UsernamePasswordAuthenticationToken.authenticated(
                "owner@example.test", "", java.util.List.of());
        when(users.findByEmail("owner@example.test")).thenReturn(Optional.of(owner));
    }

    @Test
    void createDerivesOwnerFromAuthenticatedPrincipalAndReturnsManagedWorkspaceId() throws Exception {
        Workspace workspace = new Workspace(owner, "Platform Docs", null);
        ReflectionTestUtils.setField(workspace, "id", "workspace-123e4567-e89b-12d3-a456-426614174000");
        when(workspaces.create(eq(owner), any(WorkspaceRequest.class))).thenReturn(workspace);

        mvc.perform(post("/api/managed-workspaces").principal(authentication)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Platform Docs\",\"description\":null}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(workspace.getId()))
                .andExpect(jsonPath("$.ownerId").value(73));
        verify(workspaces).create(eq(owner), any(WorkspaceRequest.class));
    }

    @Test
    void rejectsUnsupportedOwnerIdFieldInsteadOfIgnoringIt() throws Exception {
        mvc.perform(post("/api/managed-workspaces").principal(authentication)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Platform Docs\",\"ownerId\":999}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsInvalidNameAndDescription() throws Exception {
        mvc.perform(post("/api/managed-workspaces").principal(authentication)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"  \",\"description\":\"ok\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(post("/api/managed-workspaces").principal(authentication)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Valid\",\"description\":\"" + "x".repeat(1001) + "\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/api/managed-workspaces"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void memberManagementUsesAuthenticatedWorkspaceOwnerAndReturnsMinimalUserData() throws Exception {
        User member = new User("member@example.test", "unused", "Member", "Test", "DEVELOPER", true);
        member.setUsername("member");
        ReflectionTestUtils.setField(member, "id", 91L);
        when(workspaces.listMembers(owner, "workspace-shared")).thenReturn(java.util.List.of(member));
        when(workspaces.addMember(owner, "workspace-shared", 91L)).thenReturn(member);

        mvc.perform(get("/api/managed-workspaces/workspace-shared/members").principal(authentication))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].userId").value(91))
                .andExpect(jsonPath("$[0].username").value("member"))
                .andExpect(jsonPath("$[0].displayName").value("Member Test"))
                .andExpect(jsonPath("$[0].email").doesNotExist());
        mvc.perform(post("/api/managed-workspaces/workspace-shared/members").principal(authentication)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"userId\":91}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.userId").value(91));
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .delete("/api/managed-workspaces/workspace-shared/members/91").principal(authentication))
                .andExpect(status().isNoContent());

        verify(workspaces).listMembers(owner, "workspace-shared");
        verify(workspaces).addMember(owner, "workspace-shared", 91L);
        verify(workspaces).removeMember(owner, "workspace-shared", 91L);
    }
}



