package com.livingdocs.github.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.CodeEntityResponse;
import com.livingdocs.github.dto.DocumentationArtifactResponse;
import com.livingdocs.github.entity.CodeEntity;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.DocumentationArtifact;
import com.livingdocs.github.entity.DocumentationCodeRelationship;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.CodeEntityRepository;
import com.livingdocs.github.repository.DocumentationArtifactRepository;
import com.livingdocs.github.repository.DocumentationCodeRelationshipRepository;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.util.UriUtils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class DocumentationCodeRelationshipService {
    private final RepositorySyncService repositorySyncService;
    private final DocumentationArtifactRepository documentationRepository;
    private final CodeEntityRepository codeEntityRepository;
    private final DocumentationCodeRelationshipRepository relationshipRepository;

    public DocumentationCodeRelationshipService(
            RepositorySyncService repositorySyncService,
            DocumentationArtifactRepository documentationRepository,
            CodeEntityRepository codeEntityRepository,
            DocumentationCodeRelationshipRepository relationshipRepository) {
        this.repositorySyncService = repositorySyncService;
        this.documentationRepository = documentationRepository;
        this.codeEntityRepository = codeEntityRepository;
        this.relationshipRepository = relationshipRepository;
    }

    @Transactional
    public UUID recordGeneration(String userId, UUID repositoryId, String jobId, JsonNode analysis,
                                 RepositorySnapshot snapshot) {
        ConnectedRepository repo = repositorySyncService.requireOwnedRepository(userId, repositoryId);
        DocumentationArtifact artifact = documentationRepository.findByGenerationJobId(jobId)
                .orElseGet(DocumentationArtifact::new);
        artifact.setRepositoryId(repositoryId);
        artifact.setOwnerUserId(userId);
        artifact.setGenerationJobId(jobId);
        artifact.setSourceCommit(snapshot.headCommit() == null ? null : snapshot.headCommit().sha());
        documentationRepository.save(artifact);

        Set<String> presentPaths = new LinkedHashSet<>();
        for (RepositorySnapshot.SourceFile file : snapshot.files()) {
            presentPaths.add(file.path());
        }
        if (snapshot.stats() != null && !snapshot.stats().treeTruncated() && !snapshot.stats().fileLimitReached()) {
            codeEntityRepository.findByRepositoryIdAndActiveTrue(repositoryId).stream()
                    .filter(entity -> !presentPaths.contains(entity.getPath()))
                    .forEach(entity -> entity.setActive(false));
        }

        JsonNode files = analysis.path("files");
        if (files.isArray()) {
            Set<String> seenKeys = new HashSet<>();
            for (JsonNode file : files) {
                String path = text(file, "path");
                if (path == null || path.isBlank()) continue;
                String analysisStatus = text(file, "status");
                if (analysisStatus != null && !analysisStatus.equals("ok") && !analysisStatus.equals("empty")) continue;

                codeEntityRepository.findByRepositoryIdAndPathAndActiveTrue(repositoryId, path)
                        .forEach(entity -> entity.setActive(false));

                for (JsonNode item : file.path("classes")) {
                    String className = text(item, "name");
                    upsert(repo, snapshot, path, "class", className,
                            firstInteger(item, "lineno", "line_start"),
                            firstInteger(item, "end_lineno", "line_end"),
                            seenKeys);
                    for (JsonNode method : item.path("methods")) {
                        upsert(repo, snapshot, path, "method", qualify(className, text(method, "name")),
                                firstInteger(method, "lineno", "line_start"),
                                firstInteger(method, "end_lineno", "line_end"),
                                seenKeys);
                    }
                }
                for (JsonNode item : file.path("functions")) {
                    upsert(repo, snapshot, path, "function", text(item, "name"),
                            firstInteger(item, "lineno", "line_start"),
                            firstInteger(item, "end_lineno", "line_end"),
                            seenKeys);
                }
                for (JsonNode item : file.path("endpoints")) {
                    String httpMethod = text(item, "http_method");
                    String routePath = text(item, "path");
                    if (httpMethod == null || httpMethod.isBlank() || routePath == null || routePath.isBlank()) {
                        continue;
                    }
                    String name = httpMethod.trim() + " " + routePath.trim();
                    upsert(repo, snapshot, path, "endpoint", name,
                            firstInteger(item, "lineno", "line_start"),
                            firstInteger(item, "end_lineno", "line_end"),
                            seenKeys);
                }
            }
        }
        return artifact.getId();
    }

    @Transactional
    public void saveGeneratedMarkdown(String userId, String jobId, String markdown) {
        DocumentationArtifact artifact = documentationRepository.findByGenerationJobId(jobId)
                .filter(item -> item.getOwnerUserId().equals(userId))
                .orElseThrow(() -> ApiException.notFound("Generated documentation record not found."));
        artifact.setMarkdown(markdown);
    }

    @Transactional(readOnly = true)
    public List<CodeEntityResponse> listCodeEntities(String userId, UUID repositoryId) {
        repositorySyncService.requireOwnedRepository(userId, repositoryId);
        return codeEntityRepository.findByRepositoryIdAndActiveTrueOrderByPathAscLineStartAsc(repositoryId)
                .stream().map(CodeEntityResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public List<DocumentationArtifactResponse> listDocuments(String userId, UUID repositoryId) {
        repositorySyncService.requireOwnedRepository(userId, repositoryId);
        return documentationRepository.findByRepositoryIdAndOwnerUserIdOrderByCreatedAtDesc(repositoryId, userId)
                .stream().map(DocumentationArtifactResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public DocumentationArtifactResponse getDocument(String userId, UUID documentId) {
        return DocumentationArtifactResponse.from(requireDocument(userId, documentId));
    }

    @Transactional
    public List<CodeEntityResponse> replaceLinks(String userId, UUID documentId, List<UUID> ids) {
        DocumentationArtifact document = requireDocument(userId, documentId);
        Set<UUID> uniqueIds = new LinkedHashSet<>(ids);
        List<CodeEntity> targets = uniqueIds.isEmpty() ? List.of()
                : codeEntityRepository.findByIdInAndRepositoryIdAndActiveTrue(
                        List.copyOf(uniqueIds), document.getRepositoryId());
        if (targets.size() != uniqueIds.size()) {
            throw ApiException.badRequest(
                    "One or more code entities are missing, inactive, or belong to another repository.");
        }
        relationshipRepository.deleteByDocumentationId(documentId);
        relationshipRepository.flush();
        Map<UUID, CodeEntity> targetById = targets.stream()
                .collect(Collectors.toMap(CodeEntity::getId, Function.identity()));
        for (UUID targetId : uniqueIds) {
            DocumentationCodeRelationship relation = new DocumentationCodeRelationship();
            relation.setDocumentationId(documentId);
            relation.setCodeEntityId(targetId);
            relationshipRepository.save(relation);
        }
        return uniqueIds.stream()
                .map(targetById::get)
                .map(CodeEntityResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<CodeEntityResponse> relatedCode(String userId, UUID documentId) {
        DocumentationArtifact document = requireDocument(userId, documentId);
        List<DocumentationCodeRelationship> links = relationshipRepository.findByDocumentationId(documentId);
        if (links.isEmpty()) return List.of();

        List<UUID> entityIds = links.stream().map(DocumentationCodeRelationship::getCodeEntityId).toList();
        Map<UUID, CodeEntity> entitiesById = codeEntityRepository.findAllById(entityIds).stream()
                .filter(entity -> entity.isActive() && entity.getRepositoryId().equals(document.getRepositoryId()))
                .collect(Collectors.toMap(CodeEntity::getId, Function.identity()));
        return entityIds.stream()
                .map(entitiesById::get)
                .filter(Objects::nonNull)
                .map(CodeEntityResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<DocumentationArtifactResponse> relatedDocuments(String userId, UUID entityId) {
        CodeEntity entity = codeEntityRepository.findById(entityId)
                .filter(CodeEntity::isActive)
                .orElseThrow(() -> ApiException.notFound("Code entity not found."));
        repositorySyncService.requireOwnedRepository(userId, entity.getRepositoryId());
        List<DocumentationCodeRelationship> links = relationshipRepository.findByCodeEntityId(entityId);
        if (links.isEmpty()) return List.of();

        List<UUID> documentIds = links.stream().map(DocumentationCodeRelationship::getDocumentationId).toList();
        Map<UUID, DocumentationArtifact> docsById = documentationRepository
                .findByIdInAndOwnerUserId(documentIds, userId).stream()
                .filter(document -> document.getRepositoryId().equals(entity.getRepositoryId()))
                .collect(Collectors.toMap(DocumentationArtifact::getId, Function.identity()));
        return documentIds.stream()
                .map(docsById::get)
                .filter(Objects::nonNull)
                .map(DocumentationArtifactResponse::from)
                .toList();
    }

    private DocumentationArtifact requireDocument(String userId, UUID documentId) {
        DocumentationArtifact document = documentationRepository.findByIdAndOwnerUserId(documentId, userId)
                .orElseThrow(() -> ApiException.notFound("Documentation record not found."));
        repositorySyncService.requireOwnedRepository(userId, document.getRepositoryId());
        return document;
    }

    private void upsert(ConnectedRepository repository, RepositorySnapshot snapshot, String path,
                        String type, String name, Integer lineStart, Integer lineEnd,
                        Set<String> seenKeys) {
        if (name == null || name.isBlank()) return;
        String naturalKey = path + "\u0000" + type + "\u0000" + name;
        String key = sha256(naturalKey);
        if (!seenKeys.add(key)) {
            return;
        }
        CodeEntity entity = codeEntityRepository.findByRepositoryIdAndStableKey(repository.getId(), key)
                .orElseGet(CodeEntity::new);
        entity.setRepositoryId(repository.getId());
        entity.setStableKey(key);
        entity.setEntityType(type);
        entity.setName(name);
        entity.setPath(path);
        entity.setLineStart(lineStart);
        entity.setLineEnd(lineEnd);
        entity.setSourceCommit(snapshot.headCommit() == null ? null : snapshot.headCommit().sha());
        entity.setSourceUrl(sourceUrl(repository.getHtmlUrl(), snapshot, path, lineStart, lineEnd));
        entity.setActive(true);
        codeEntityRepository.saveAndFlush(entity);
    }

    private String sourceUrl(String base, RepositorySnapshot snapshot, String path, Integer start, Integer end) {
    String repoUrl = (base == null || base.isBlank())
            ? "https://github.com/" + snapshot.repository().fullName()
            : base;
    String ref = snapshot.headCommit() != null && snapshot.headCommit().sha() != null
            ? snapshot.headCommit().sha()
            : snapshot.branch();
    String url = repoUrl.replaceAll("/$", "") + "/blob/" + ref + "/"
            + UriUtils.encodePath(path, StandardCharsets.UTF_8);
    if (start != null && start > 0) {
        url += "#L" + start + (end != null && end >= start ? "-L" + end : "");
    }
    return url;
}

    private String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isTextual() ? value.asText() : null;
    }

    private Integer firstInteger(JsonNode node, String primaryField, String fallbackField) {
        if (node.path(primaryField).isInt()) {
            return node.path(primaryField).intValue();
        }
        return node.path(fallbackField).isInt() ? node.path(fallbackField).intValue() : null;
    }

    private String qualify(String parent, String name) {
        if (name == null) return parent;
        return parent == null || parent.isBlank() ? name : parent + "." + name;
    }
}