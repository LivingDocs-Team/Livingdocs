package com.cnpm.backend.dto;

import com.cnpm.backend.entity.User;

public record WorkspaceMemberResponse(Long userId, String username, String displayName) {
    public static WorkspaceMemberResponse from(User user) {
        return new WorkspaceMemberResponse(user.getId(), user.getUsername(),
                (user.getFirstName() + " " + user.getLastName()).trim());
    }
}



