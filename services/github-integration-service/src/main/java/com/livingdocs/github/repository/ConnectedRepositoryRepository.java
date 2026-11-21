package com.livingdocs.github.repository;

import com.livingdocs.github.entity.ConnectedRepository;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ConnectedRepositoryRepository extends JpaRepository<ConnectedRepository, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select repo from ConnectedRepository repo where repo.id = :id")
    Optional<ConnectedRepository> lockById(@Param("id") UUID id);

    List<ConnectedRepository> findByWorkspaceIdOrderByFullNameAsc(String workspaceId);

    List<ConnectedRepository> findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(
            String workspaceId, UUID connectionId);

    List<ConnectedRepository> findByConnectionId(UUID connectionId);

    /** LD-68: mọi workspace đã thêm repo GitHub này (webhook chỉ biết id repo trên GitHub). */
    List<ConnectedRepository> findByGithubRepoId(Long githubRepoId);

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
