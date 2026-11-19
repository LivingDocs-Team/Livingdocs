package com.livingdocs.github.repository;

import com.livingdocs.github.entity.SourceChange;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface SourceChangeRepository extends JpaRepository<SourceChange, UUID> {

    Optional<SourceChange> findByRepositoryIdAndTriggerTypeAndCommitSha(
            UUID repositoryId, SourceChange.Trigger triggerType, String commitSha);

    List<SourceChange> findByRepositoryIdOrderByCreatedAtDesc(UUID repositoryId, Pageable pageable);
}
