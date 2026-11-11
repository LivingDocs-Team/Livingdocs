package com.cnpm.backend.service;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.dto.WorkspaceRequest;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.entity.Workspace;
import com.cnpm.backend.entity.WorkspaceMembership;
import com.cnpm.backend.repository.WorkspaceRepository;
import com.cnpm.backend.repository.WorkspaceMembershipRepository;
import com.cnpm.backend.repository.UserRepository;

@Service
public class WorkspaceService {

    private final WorkspaceRepository workspaceRepository;
    private final WorkspaceMembershipRepository membershipRepository;
    private final UserRepository userRepository;

    public WorkspaceService(WorkspaceRepository workspaceRepository,
            WorkspaceMembershipRepository membershipRepository, UserRepository userRepository) {
        this.workspaceRepository = workspaceRepository;
        this.membershipRepository = membershipRepository;
        this.userRepository = userRepository;
    }

    @Transactional
    public Workspace create(User owner, WorkspaceRequest request) {
        Workspace workspace = new Workspace(owner, normalizeName(request.getName()),
                normalizeDescription(request.getDescription()));
        return workspaceRepository.save(workspace);
    }

    @Transactional(readOnly = true)
    public List<Workspace> listForOwner(User owner) {
        return workspaceRepository.findAllByOwner_IdOrderByCreatedAtDescIdAsc(owner.getId());
    }

    @Transactional(readOnly = true)
    public List<Workspace> listForUser(User user) {
        return workspaceRepository.findAllAccessibleByUserId(user.getId());
    }

    @Transactional(readOnly = true)
    public Workspace getForOwner(User owner, String workspaceId) {
        return workspaceRepository.findByIdAndOwner_Id(workspaceId, owner.getId())
                .orElseThrow(WorkspaceService::notFound);
    }

    @Transactional(readOnly = true)
    public Workspace getForMemberOrOwner(User actor, String workspaceId) {
        Workspace workspace = workspaceRepository.findById(workspaceId)
                .orElseThrow(WorkspaceService::notFound);
        if (!workspace.getOwner().getId().equals(actor.getId())
                && !membershipRepository.existsByWorkspace_IdAndUser_IdAndUser_ActiveTrue(workspaceId, actor.getId())) {
            throw notFoundException();
        }
        return workspace;
    }

    @Transactional(readOnly = true)
    public boolean isOwnerOrMember(Long userId, String workspaceId) {
        return workspaceRepository.findById(workspaceId)
                .map(workspace -> workspace.getOwner().getId().equals(userId)
                        || membershipRepository.existsByWorkspace_IdAndUser_IdAndUser_ActiveTrue(workspaceId, userId))
                .orElse(false);
    }

    @Transactional
    public List<User> listMembers(User owner, String workspaceId) {
        Workspace workspace = getForOwner(owner, workspaceId);
        return membershipRepository.findAllByWorkspace_IdOrderByUser_IdAsc(workspace.getId()).stream()
                .map(WorkspaceMembership::getUser).toList();
    }

    @Transactional
    public User addMember(User owner, String workspaceId, Long targetUserId) {
        Workspace workspace = workspaceRepository.findByIdAndOwnerIdForUpdate(workspaceId, owner.getId())
                .orElseThrow(WorkspaceService::notFound);
        if (targetUserId == null || targetUserId <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid userId is required");
        }
        if (owner.getId().equals(targetUserId)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The workspace owner cannot be added as a member");
        }
        User member = userRepository.findById(targetUserId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found"));
        if (membershipRepository.existsByWorkspace_IdAndUser_Id(workspaceId, targetUserId)) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "User is already a workspace member");
        }
        membershipRepository.save(new WorkspaceMembership(workspace, member));
        return member;
    }

    @Transactional
    public void removeMember(User owner, String workspaceId, Long targetUserId) {
        workspaceRepository.findByIdAndOwnerIdForUpdate(workspaceId, owner.getId())
                .orElseThrow(WorkspaceService::notFound);
        if (targetUserId == null || targetUserId <= 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid userId is required");
        }
        membershipRepository.deleteByWorkspace_IdAndUser_Id(workspaceId, targetUserId);
    }

    @Transactional
    public Workspace update(User owner, String workspaceId, WorkspaceRequest request) {
        Workspace workspace = getForOwner(owner, workspaceId);
        workspace.setName(normalizeName(request.getName()));
        workspace.setDescription(normalizeDescription(request.getDescription()));
        return workspaceRepository.save(workspace);
    }

    private static String normalizeName(String name) {
        if (name == null || name.isBlank() || name.trim().length() > 100) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Workspace name must contain 1 to 100 characters");
        }
        return name.trim();
    }

    private static String normalizeDescription(String description) {
        if (description != null && description.length() > 1000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Workspace description must not exceed 1000 characters");
        }
        return description == null || description.isBlank() ? null : description.trim();
    }

    private static ResponseStatusException notFound() {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found");
    }

    private static ResponseStatusException notFoundException() { return notFound(); }
}
