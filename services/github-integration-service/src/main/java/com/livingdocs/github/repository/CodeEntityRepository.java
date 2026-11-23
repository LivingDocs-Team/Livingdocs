package com.livingdocs.github.repository;

import com.livingdocs.github.entity.CodeEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface CodeEntityRepository extends JpaRepository<CodeEntity, UUID> {
    Optional<CodeEntity> findByRepositoryIdAndStableKey(UUID repositoryId, String stableKey);
    List<CodeEntity> findByRepositoryIdAndActiveTrue(UUID repositoryId);
    List<CodeEntity> findByRepositoryIdAndPathAndActiveTrue(UUID repositoryId, String path);
    List<CodeEntity> findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(UUID repositoryId);
    List<CodeEntity> findByIdInAndRepositoryIdAndActiveTrue(List<UUID> ids, UUID repositoryId);

    long countByRepositoryIdAndActiveTrue(UUID repositoryId);

    long countByActiveTrue();

    @Query("""
            select count(e) from CodeEntity e where e.active = true
              and exists (select 1 from DocumentationCodeRelationship r where r.codeEntityId = e.id)""")
    long countDocumented();

    /** Active code entities of the repository that no documentation is linked to. */
    @Query("""
            select e from CodeEntity e
            where e.repositoryId = :repositoryId and e.active = true
              and not exists (select 1 from DocumentationCodeRelationship r where r.codeEntityId = e.id)
            order by e.path asc, e.lineStart asc""")
    List<CodeEntity> findUndocumented(@Param("repositoryId") UUID repositoryId);
}
