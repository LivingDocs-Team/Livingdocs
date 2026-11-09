package com.cnpm.backend.dto;

import java.time.LocalDateTime;

import com.cnpm.backend.entity.Workspace;

public record WorkspaceResponse(
        String id,
        String name,
        String description,
        Long ownerId,
        LocalDateTime createdAt,
        LocalDateTime updatedAt,
        String accessRole) {

    public static WorkspaceResponse from(Workspace workspace) {
        return from(workspace, workspace.getOwner().getId());
    }

    public static WorkspaceResponse from(Workspace workspace, Long viewerId) {
        boolean owner = workspace.getOwner().getId().equals(viewerId);
        return new WorkspaceResponse(workspace.getId(), workspace.getName(),
                workspace.getDescription(), owner ? workspace.getOwner().getId() : null,
                workspace.getCreatedAt(), workspace.getUpdatedAt(), owner ? "OWNER" : "MEMBER");
    }
}
