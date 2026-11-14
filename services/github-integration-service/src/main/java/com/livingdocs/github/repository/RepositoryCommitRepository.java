package com.livingdocs.github.repository;

import com.livingdocs.github.entity.RepositoryCommit;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface RepositoryCommitRepository extends JpaRepository<RepositoryCommit, UUID> {

    Optional<RepositoryCommit> findByRepositoryIdAndSha(UUID repositoryId, String sha);

    List<RepositoryCommit> findByRepositoryIdOrderByCommittedAtDesc(UUID repositoryId, Pageable pageable);
}



