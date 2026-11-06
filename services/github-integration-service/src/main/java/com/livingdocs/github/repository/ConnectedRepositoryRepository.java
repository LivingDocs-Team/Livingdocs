package com.livingdocs.github.repository;

import com.livingdocs.github.entity.ConnectedRepository;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface ConnectedRepositoryRepository extends JpaRepository<ConnectedRepository, UUID> {

    List<ConnectedRepository> findByWorkspaceIdOrderByFullNameAsc(String workspaceId);

    List<ConnectedRepository> findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(
            String workspaceId, UUID connectionId);

    List<ConnectedRepository> findByConnectionId(UUID connectionId);

    /** LD-68: mọi workspace đã thêm repo GitHub này (webhook chỉ biết id repo trên GitHub). */
    List<ConnectedRepository> findByGithubRepoId(Long githubRepoId);

    boolean existsByWorkspaceIdAndGithubRepoId(String workspaceId, Long githubRepoId);

    boolean existsByWorkspaceIdAndConnectionIdAndGithubRepoId(
            String workspaceId, UUID connectionId, Long githubRepoId);
}
