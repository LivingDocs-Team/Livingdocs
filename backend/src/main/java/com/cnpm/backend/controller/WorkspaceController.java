package com.cnpm.backend.controller;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.dto.WorkspaceRequest;
import com.cnpm.backend.dto.WorkspaceResponse;
import com.cnpm.backend.dto.WorkspaceMemberRequest;
import com.cnpm.backend.dto.WorkspaceMemberResponse;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.service.WorkspaceService;

import jakarta.validation.Valid;

@RestController
@Validated
@RequestMapping("/api/managed-workspaces")
public class WorkspaceController {

    private final WorkspaceService workspaceService;
    private final UserRepository userRepository;

    public WorkspaceController(WorkspaceService workspaceService, UserRepository userRepository) {
        this.workspaceService = workspaceService;
        this.userRepository = userRepository;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    public WorkspaceResponse create(@Valid @RequestBody WorkspaceRequest request,
            Authentication authentication) {
        User owner = authenticatedUser(authentication);
        return WorkspaceResponse.from(workspaceService.create(owner, request));
    }

    @GetMapping
    @Transactional(readOnly = true)
    public List<WorkspaceResponse> list(Authentication authentication) {
        User actor = authenticatedUser(authentication);
        return workspaceService.listForUser(actor).stream()
                .map(workspace -> WorkspaceResponse.from(workspace, actor.getId())).toList();
    }

    @GetMapping("/{workspaceId}")
    @Transactional(readOnly = true)
    public WorkspaceResponse get(@PathVariable String workspaceId, Authentication authentication) {
        User actor = authenticatedUser(authentication);
        return WorkspaceResponse.from(workspaceService.getForMemberOrOwner(actor, workspaceId), actor.getId());
    }

    @GetMapping("/{workspaceId}/members")
    @Transactional(readOnly = true)
    public List<WorkspaceMemberResponse> members(@PathVariable String workspaceId,
            Authentication authentication) {
        return workspaceService.listMembers(authenticatedUser(authentication), workspaceId).stream()
                .map(WorkspaceMemberResponse::from).toList();
    }

    @PostMapping("/{workspaceId}/members")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    public WorkspaceMemberResponse addMember(@PathVariable String workspaceId,
            @Valid @RequestBody WorkspaceMemberRequest request, Authentication authentication) {
        User member = workspaceService.addMember(authenticatedUser(authentication), workspaceId, request.userId());
        return WorkspaceMemberResponse.from(member);
    }

    @DeleteMapping("/{workspaceId}/members/{userId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void removeMember(@PathVariable String workspaceId, @PathVariable Long userId,
            Authentication authentication) {
        workspaceService.removeMember(authenticatedUser(authentication), workspaceId, userId);
    }

    @PutMapping("/{workspaceId}")
    @Transactional
    public WorkspaceResponse update(@PathVariable String workspaceId,
            @Valid @RequestBody WorkspaceRequest request, Authentication authentication) {
        return WorkspaceResponse.from(workspaceService.update(
                authenticatedUser(authentication), workspaceId, request));
    }

    private User authenticatedUser(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (authentication.getPrincipal() instanceof OAuth2User oauth2User) {
            Object githubId = oauth2User.getAttribute("id");
            if (githubId == null) {
                throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
            }
            return userRepository.findByGithubId(String.valueOf(githubId))
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        }
        String email = authentication.getPrincipal() instanceof UserDetails details
                ? details.getUsername() : authentication.getName();
        return userRepository.findByEmail(email)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
    }
}
