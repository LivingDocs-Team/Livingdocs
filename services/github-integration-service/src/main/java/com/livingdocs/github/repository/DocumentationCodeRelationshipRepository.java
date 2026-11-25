package com.livingdocs.github.repository;

import com.livingdocs.github.entity.DocumentationCodeRelationship;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface DocumentationCodeRelationshipRepository extends JpaRepository<DocumentationCodeRelationship, UUID> {
    List<DocumentationCodeRelationship> findByDocumentationId(UUID documentationId);
    List<DocumentationCodeRelationship> findByCodeEntityId(UUID codeEntityId);
    void deleteByDocumentationId(UUID documentationId);

    /** Which documents describe which source files, with the number of linked code entities (strongest first). */
    @org.springframework.data.jpa.repository.Query("""
            select r.documentationId, e.path, count(e) from DocumentationCodeRelationship r, CodeEntity e
            where r.codeEntityId = e.id and e.active = true
            group by r.documentationId, e.path order by count(e) desc, e.path asc""")
    List<Object[]> dependencyEdges(org.springframework.data.domain.Pageable pageable);

    /** The same graph restricted to the repositories the caller may see. */
    @org.springframework.data.jpa.repository.Query("""
            select r.documentationId, e.path, count(e) from DocumentationCodeRelationship r, CodeEntity e
            where r.codeEntityId = e.id and e.active = true and e.repositoryId in :repositoryIds
            group by r.documentationId, e.path order by count(e) desc, e.path asc""")
    List<Object[]> dependencyEdgesIn(
            @org.springframework.data.repository.query.Param("repositoryIds") java.util.Collection<UUID> repositoryIds,
            org.springframework.data.domain.Pageable pageable);
}
