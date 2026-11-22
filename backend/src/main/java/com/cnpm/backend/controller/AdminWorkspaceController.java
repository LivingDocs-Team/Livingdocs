package com.cnpm.backend.controller;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.dto.WorkspaceMemberRequest;
import com.cnpm.backend.dto.WorkspaceMemberResponse;
import com.cnpm.backend.dto.WorkspaceRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.entity.Workspace;
import com.cnpm.backend.entity.WorkspaceMembership;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.WorkspaceMembershipRepository;
import com.cnpm.backend.repository.WorkspaceRepository;

import jakarta.validation.Valid;

@RestController
@Validated
@RequestMapping("/api/admin/workspaces")
@PreAuthorize("hasAnyRole('ADMIN', 'ADMINISTRATOR') and @systemAdminAccess.allows(authentication)")
public class AdminWorkspaceController {

    private final WorkspaceRepository workspaceRepository;
    private final WorkspaceMembershipRepository membershipRepository;
    private final UserRepository userRepository;

    public AdminWorkspaceController(
            WorkspaceRepository workspaceRepository,
            WorkspaceMembershipRepository membershipRepository,
            UserRepository userRepository) {
        this.workspaceRepository = workspaceRepository;
        this.membershipRepository = membershipRepository;
        this.userRepository = userRepository;
    }

    @GetMapping
    @Transactional(readOnly = true)
    public List<AdminWorkspaceSummary> listAllWorkspaces() {
        return workspaceRepository.findAll(Sort.by(Sort.Direction.DESC, "createdAt").and(Sort.by(Sort.Direction.ASC, "id")))
                .stream()
                .map(this::toSummary)
                .toList();
    }

    @PutMapping("/{workspaceId}")
    @Transactional
    public AdminWorkspaceSummary updateWorkspace(
            @PathVariable String workspaceId,
            @Valid @RequestBody WorkspaceRequest request) {
        Workspace workspace = workspaceRepository.findById(workspaceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
        String name = request.getName() == null ? "" : request.getName().trim();
        if (name.isEmpty() || name.length() > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Workspace name must contain 1 to 100 characters");
        }
        String description = request.getDescription();
        if (description != null && description.length() > 1000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Workspace description must not exceed 1000 characters");
        }
        workspace.setName(name);
        workspace.setDescription(description == null || description.isBlank() ? null : description.trim());
        return toSummary(workspaceRepository.save(workspace));
    }

    @GetMapping("/{workspaceId}/members")
    @Transactional(readOnly = true)
    public List<WorkspaceMemberResponse> listMembers(@PathVariable String workspaceId) {
        Workspace workspace = workspaceRepository.findById(workspaceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
        return membershipRepository.findAllByWorkspace_IdOrderByUser_IdAsc(workspace.getId()).stream()
                .map(WorkspaceMembership::getUser)
                .map(WorkspaceMemberResponse::from)
                .toList();
    }

    @PostMapping("/{workspaceId}/members")
    @ResponseStatus(HttpStatus.CREATED)
    @Transactional
    public WorkspaceMemberResponse addMember(
            @PathVariable String workspaceId,
            @Valid @RequestBody WorkspaceMemberRequest request) {
        Workspace workspace = workspaceRepository.findById(workspaceId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found"));
        Long targetUserId = request.userId();
        if (targetUserId == null || targetUserId <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid userId is required");
        }
        if (workspace.getOwner().getId().equals(targetUserId)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The workspace owner cannot be added as a member");
        }
        User member = userRepository.findById(targetUserId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found"));
        if (membershipRepository.existsByWorkspace_IdAndUser_Id(workspaceId, targetUserId)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "User is already a workspace member");
        }
        membershipRepository.save(new WorkspaceMembership(workspace, member));
        return WorkspaceMemberResponse.from(member);
    }

    @DeleteMapping("/{workspaceId}/members/{userId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Transactional
    public void removeMember(@PathVariable String workspaceId, @PathVariable Long userId) {
        if (!workspaceRepository.existsById(workspaceId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found");
        }
        if (userId == null || userId <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid userId is required");
        }
        membershipRepository.deleteByWorkspace_IdAndUser_Id(workspaceId, userId);
    }

    private AdminWorkspaceSummary toSummary(Workspace workspace) {
        User owner = workspace.getOwner();
        int memberCount = membershipRepository.findAllByWorkspace_IdOrderByUser_IdAsc(workspace.getId()).size();
        return new AdminWorkspaceSummary(
                workspace.getId(),
                workspace.getName(),
                workspace.getDescription(),
                owner.getId(),
                owner.getEmail(),
                owner.getUsername(),
                memberCount,
                workspace.getCreatedAt());
    }

    public record AdminWorkspaceSummary(
            String id,
            String name,
            String description,
            Long ownerId,
            String ownerEmail,
            String ownerUsername,
            int memberCount,
            LocalDateTime createdAt) {}
}