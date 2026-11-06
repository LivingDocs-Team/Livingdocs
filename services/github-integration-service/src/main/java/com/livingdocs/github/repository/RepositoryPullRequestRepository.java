package com.livingdocs.github.repository;

import com.livingdocs.github.entity.RepositoryPullRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface RepositoryPullRequestRepository extends JpaRepository<RepositoryPullRequest, UUID> {

    Optional<RepositoryPullRequest> findByRepositoryIdAndNumber(UUID repositoryId, Integer number);

    List<RepositoryPullRequest> findByRepositoryIdOrderByUpdatedAtDesc(UUID repositoryId, Pageable pageable);
}
