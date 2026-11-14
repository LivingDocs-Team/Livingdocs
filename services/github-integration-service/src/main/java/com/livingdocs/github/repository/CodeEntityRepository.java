package com.livingdocs.github.repository;

import com.livingdocs.github.entity.CodeEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface CodeEntityRepository extends JpaRepository<CodeEntity, UUID> {
    Optional<CodeEntity> findByRepositoryIdAndStableKey(UUID repositoryId, String stableKey);
    List<CodeEntity> findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(UUID repositoryId);
    List<CodeEntity> findByIdInAndRepositoryIdAndActiveTrue(List<UUID> ids, UUID repositoryId);
}



