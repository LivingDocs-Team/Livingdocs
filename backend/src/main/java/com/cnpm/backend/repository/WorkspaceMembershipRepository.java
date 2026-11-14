package com.cnpm.backend.repository;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import com.cnpm.backend.entity.WorkspaceMembership;

public interface WorkspaceMembershipRepository extends JpaRepository<WorkspaceMembership, Long> {

    boolean existsByWorkspace_IdAndUser_Id(String workspaceId, Long userId);

    boolean existsByWorkspace_IdAndUser_IdAndUser_ActiveTrue(String workspaceId, Long userId);

    List<WorkspaceMembership> findAllByWorkspace_IdOrderByUser_IdAsc(String workspaceId);

    void deleteByWorkspace_IdAndUser_Id(String workspaceId, Long userId);
}



