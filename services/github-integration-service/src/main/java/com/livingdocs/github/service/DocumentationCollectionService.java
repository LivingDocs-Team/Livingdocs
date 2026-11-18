package com.livingdocs.github.service;

import com.livingdocs.github.exception.ApiException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Locale;
import java.util.UUID;

@Service
public class DocumentationCollectionService {
    private final JdbcClient jdbc;

    public DocumentationCollectionService(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public record Collection(UUID id, String name, String description, UUID repositoryId, String repositoryName) {}
    public record Document(UUID id, String title, String assignedOwnerId) {}

    private static final String COLLECTIONS = """
            SELECT c.id, c.name, c.description, r.id AS repository_id, r.full_name AS repository_name
            FROM documentation_collections c
            LEFT JOIN repositories r ON r.id = c.repository_id AND r.workspace_id = c.workspace_id
                AND r.status <> 'DISCONNECTED'
            WHERE c.workspace_id = ?
            """;

    private static final String DOCUMENTS = """
            SELECT d.id, COALESCE(NULLIF(TRIM(SUBSTRING(d.markdown FROM '(?n)^# +([^\r\n]+)')), ''),
                        CONCAT('Document ', CAST(d.id AS VARCHAR))) AS title,
                   CAST(o.owner_user_id AS VARCHAR) AS assigned_owner_id
            FROM documentation_artifacts d
            LEFT JOIN documentation_owner_assignments o ON o.document_id = d.id AND o.workspace_id = ?
            WHERE d.repository_id = ? AND d.markdown IS NOT NULL
            """;

    @Transactional(readOnly = true)
    public List<Collection> list(String workspace) {
        return jdbc.sql(COLLECTIONS + " ORDER BY LOWER(c.name), c.id")
                .param(workspace).query(Collection.class).list();
    }

    @Transactional
    public Collection save(String workspace, UUID id, String name, String description, UUID repositoryId) {
        if (id != null) {
            lockedCollection(workspace, id);
        }
        if (repositoryId != null) {
            lockRepository(workspace, repositoryId);
        }
        UUID collectionId = id == null ? UUID.randomUUID() : id;
        String normalizedName = name.strip();
        String nameKey = normalizedName.toLowerCase(Locale.ROOT);
        try {
            if (id == null) {
                jdbc.sql("""
                        INSERT INTO documentation_collections (id, workspace_id, name, name_key, description, repository_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """).params(collectionId, workspace, normalizedName, nameKey, description, repositoryId).update();
            } else {
                jdbc.sql("""
                        DELETE FROM documentation_collection_documents
                        WHERE collection_id = ? AND document_id IN (
                            SELECT id FROM documentation_artifacts WHERE repository_id IS DISTINCT FROM ?
                        )
                        """).params(id, repositoryId).update();
                jdbc.sql("""
                        UPDATE documentation_collections SET name = ?, name_key = ?, description = ?, repository_id = ?
                        WHERE workspace_id = ? AND id = ?
                        """).params(normalizedName, nameKey, description, repositoryId, workspace, id).update();
            }
        } catch (DuplicateKeyException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "COLLECTION_NAME_EXISTS",
                    "A collection with this name already exists in the workspace.");
        }
        return collection(workspace, collectionId);
    }

    @Transactional
    public void delete(String workspace, UUID id) {
        if (jdbc.sql("DELETE FROM documentation_collections WHERE workspace_id = ? AND id = ?")
                .params(workspace, id).update() == 0) {
            throw ApiException.notFound("Collection not found.");
        }
    }

    @Transactional
    public List<Document> documents(String workspace, UUID collectionId, boolean candidates) {
        Collection collection = lockedCollection(workspace, collectionId);
        if (collection.repositoryId() == null) return List.of();
        lockRepository(workspace, collection.repositoryId());
        String membership = """
                 AND EXISTS (SELECT 1 FROM documentation_collection_documents m
                             WHERE m.document_id = d.id AND m.collection_id = ?)
                """;
        return jdbc.sql(DOCUMENTS + (candidates ? "" : membership) + " ORDER BY title, d.id")
                .params(candidates ? List.of(workspace, collection.repositoryId())
                        : List.of(workspace, collection.repositoryId(), collectionId))
                .query(Document.class).list();
    }

    @Transactional
    public void attach(String workspace, UUID collectionId, UUID documentId) {
        UUID repositoryId = checkedRepository(workspace, collectionId);
        int inserted = jdbc.sql("""
                INSERT INTO documentation_collection_documents (collection_id, document_id)
                SELECT ?, id FROM documentation_artifacts
                WHERE id = ? AND repository_id = ? AND markdown IS NOT NULL
                ON CONFLICT (collection_id, document_id) DO NOTHING
                """).params(collectionId, documentId, repositoryId).update();
        if (inserted == 0) requireAttached(collectionId, documentId, repositoryId);
    }

    @Transactional
    public void detach(String workspace, UUID collectionId, UUID documentId) {
        lockedCollection(workspace, collectionId);
        jdbc.sql("DELETE FROM documentation_collection_documents WHERE collection_id = ? AND document_id = ?")
                .params(collectionId, documentId).update();
    }

    @Transactional
    public void assignOwner(String workspace, UUID collectionId, UUID documentId, Long ownerUserId) {
        UUID repositoryId = checkedRepository(workspace, collectionId);
        requireAttached(collectionId, documentId, repositoryId);
        if (ownerUserId == null) {
            jdbc.sql("DELETE FROM documentation_owner_assignments WHERE workspace_id = ? AND document_id = ?")
                    .params(workspace, documentId).update();
        } else {
            jdbc.sql("""
                    INSERT INTO documentation_owner_assignments (workspace_id, document_id, owner_user_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT (workspace_id, document_id) DO UPDATE SET owner_user_id = EXCLUDED.owner_user_id
                    """).params(workspace, documentId, ownerUserId).update();
        }
    }

    private Collection collection(String workspace, UUID id) {
        return jdbc.sql(COLLECTIONS + " AND c.id = ?").params(workspace, id)
                .query(Collection.class).optional().orElseThrow(() -> ApiException.notFound("Collection not found."));
    }

    private Collection lockedCollection(String workspace, UUID id) {
        return jdbc.sql(COLLECTIONS + " AND c.id = ? FOR UPDATE OF c").params(workspace, id)
                .query(Collection.class).optional().orElseThrow(() -> ApiException.notFound("Collection not found."));
    }

    private UUID checkedRepository(String workspace, UUID collectionId) {
        UUID repositoryId = lockedCollection(workspace, collectionId).repositoryId();
        if (repositoryId == null) throw ApiException.notFound("The collection has no connected repository.");
        lockRepository(workspace, repositoryId);
        return repositoryId;
    }

    private void lockRepository(String workspace, UUID repositoryId) {
        jdbc.sql("""
                SELECT id FROM repositories
                WHERE id = ? AND workspace_id = ? AND status <> 'DISCONNECTED' FOR UPDATE
                """).params(repositoryId, workspace).query(UUID.class).optional()
                .orElseThrow(() -> ApiException.notFound("Connected repository not found in the workspace."));
    }

    private void requireAttached(UUID collectionId, UUID documentId, UUID repositoryId) {
        jdbc.sql("""
                SELECT m.document_id FROM documentation_collection_documents m
                JOIN documentation_artifacts d ON d.id = m.document_id
                WHERE m.collection_id = ? AND d.id = ? AND d.repository_id = ? AND d.markdown IS NOT NULL
                """).params(collectionId, documentId, repositoryId).query(UUID.class).optional()
                .orElseThrow(() -> ApiException.notFound("Document not found in the collection."));
    }
}
