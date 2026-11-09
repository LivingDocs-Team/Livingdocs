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

    boolean existsByWorkspaceIdAndGithubRepoId(String workspaceId, Long githubRepoId);

    boolean existsByWorkspaceIdAndConnectionIdAndGithubRepoId(
            String workspaceId, UUID connectionId, Long githubRepoId);

    boolean existsByConnectionIdAndGithubRepoIdAndWorkspaceIdNot(
            UUID connectionId, Long githubRepoId, String workspaceId);

    List<ConnectedRepository> findAllByConnectionIdAndGithubRepoIdOrderByCreatedAtAsc(
            UUID connectionId, Long githubRepoId);

    boolean existsByWorkspaceIdAndGithubRepoIdAndIdNot(
            String workspaceId, Long githubRepoId, UUID id);
}
