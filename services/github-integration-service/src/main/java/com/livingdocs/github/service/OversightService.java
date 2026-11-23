package com.livingdocs.github.service;

import com.livingdocs.github.change.AutoUpdatePolicies;
import com.livingdocs.github.dto.DocumentationArtifactResponse;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.DocumentationArtifact;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.CodeEntityRepository;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.repository.DocumentationArtifactRepository;
import com.livingdocs.github.repository.DocumentationCodeRelationshipRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Read-only views across every repository, document and workflow, for the roles that oversee the installation
 * (Technical Lead and Administrator). Nothing here shows or changes a user's secrets or GitHub tokens.
 */
@Service
public class OversightService {
    static final int GRAPH_EDGES = 300;
    private static final int DOCUMENT_LIMIT = 200;

    public record RepositorySummary(UUID id, String workspaceId, String fullName, String defaultBranch,
                                    RepositoryStatus status, Instant lastSyncedAt) {
        static RepositorySummary from(ConnectedRepository repo) {
            return new RepositorySummary(repo.getId(), repo.getWorkspaceId(), repo.getFullName(),
                    repo.getDefaultBranch(), repo.getStatus(), repo.getLastSyncedAt());
        }
    }

    public record DocumentSummary(UUID id, UUID repositoryId, String repositoryName, String title,
                                  String sourceCommit, Instant createdAt) { }

    public record Counts(long repositories, long documents, long codeEntities, long documentedEntities, int coveragePercent) { }

    public record GraphNode(String id, String kind, String label) { }

    public record GraphEdge(String from, String to, long entities) { }

    public record Health(Instant generatedAt, Counts counts, Map<String, Long> repositoriesByStatus,
                         Map<String, Long> workflowsByStatus, List<GraphNode> nodes, List<GraphEdge> edges,
                         boolean graphTruncated) { }

    private final ConnectedRepositoryRepository repositories;
    private final DocumentationArtifactRepository artifacts;
    private final CodeEntityRepository codeEntities;
    private final DocumentationCodeRelationshipRepository relationships;
    private final DocumentWorkflowRepository workflows;
    private final AutoUpdatePolicies autoUpdatePolicies;
    private final IngestionService ingestion;

    public OversightService(ConnectedRepositoryRepository repositories, DocumentationArtifactRepository artifacts,
            CodeEntityRepository codeEntities, DocumentationCodeRelationshipRepository relationships,
            DocumentWorkflowRepository workflows, AutoUpdatePolicies autoUpdatePolicies, IngestionService ingestion) {
        this.repositories = repositories;
        this.artifacts = artifacts;
        this.codeEntities = codeEntities;
        this.relationships = relationships;
        this.workflows = workflows;
        this.autoUpdatePolicies = autoUpdatePolicies;
        this.ingestion = ingestion;
    }

    /** Oversight is for the Technical Lead permission and for Administrators. */
    public static boolean mayOversee(Set<String> authorities) {
        return authorities.contains("DOCUMENT_TECHNICAL_REVIEW") || authorities.contains("ROLE_ADMINISTRATOR")
                || authorities.contains("ROLE_ADMIN");
    }

    /** Workflow reads are permission-based: the Technical Lead permission reads every workflow (view only). */
    public static boolean mayReadAllWorkflows(Set<String> authorities) {
        return authorities.contains("DOCUMENT_TECHNICAL_REVIEW");
    }

    public static void require(Set<String> authorities) {
        if (!mayOversee(authorities)) throw ApiException.forbidden("Oversight access is required.");
    }

    @Transactional(readOnly = true)
    public List<RepositorySummary> repositories() {
        return repositories.findAllByOrderByFullNameAsc().stream().map(RepositorySummary::from).toList();
    }

    @Transactional(readOnly = true)
    public ConnectedRepository repository(UUID id) {
        return repositories.findById(id).orElseThrow(() -> ApiException.notFound("Repository not found."));
    }

    @Transactional(readOnly = true)
    public Object pullRequests(UUID repositoryId) {
        repository(repositoryId);
        return ingestion.listPullRequests(repositoryId);
    }

    @Transactional(readOnly = true)
    public Object commits(UUID repositoryId) {
        repository(repositoryId);
        return ingestion.listCommits(repositoryId);
    }

    @Transactional(readOnly = true)
    public List<DocumentSummary> documents() {
        Map<UUID, String> names = new LinkedHashMap<>();
        repositories.findAll().forEach((repo) -> names.put(repo.getId(), repo.getFullName()));
        return artifacts.findAll(PageRequest.of(0, DOCUMENT_LIMIT,
                        org.springframework.data.domain.Sort.by(org.springframework.data.domain.Sort.Direction.DESC, "createdAt")))
                .stream().map((artifact) -> new DocumentSummary(artifact.getId(), artifact.getRepositoryId(),
                        names.get(artifact.getRepositoryId()), title(artifact), artifact.getSourceCommit(),
                        artifact.getCreatedAt())).toList();
    }

    @Transactional(readOnly = true)
    public DocumentationArtifactResponse document(UUID id) {
        return artifacts.findById(id).map(DocumentationArtifactResponse::from)
                .orElseThrow(() -> ApiException.notFound("Document not found."));
    }

    @Transactional(readOnly = true)
    public List<AutoUpdatePolicies.Rule> driftPolicies(UUID repositoryId) {
        repository(repositoryId);
        return autoUpdatePolicies.rulesFor(repositoryId);
    }

    @Transactional
    public List<AutoUpdatePolicies.Rule> replaceDriftPolicies(UUID repositoryId, List<AutoUpdatePolicies.Rule> rules) {
        repository(repositoryId);
        return autoUpdatePolicies.replaceUnchecked(repositoryId, rules);
    }

    @Transactional(readOnly = true)
    public Health health() {
        long total = codeEntities.countByActiveTrue();
        long documented = codeEntities.countDocumented();
        Counts counts = new Counts(repositories.count(), artifacts.count(), total, documented,
                total == 0 ? 0 : (int) Math.round(documented * 100.0 / total));

        Map<String, Long> repoStatus = new LinkedHashMap<>();
        for (RepositoryStatus status : RepositoryStatus.values()) repoStatus.put(status.name(), repositories.countByStatus(status));
        Map<String, Long> workflowStatus = new LinkedHashMap<>();
        for (DocumentWorkflowStatus status : DocumentWorkflowStatus.values()) workflowStatus.put(status.name(), workflows.countByStatus(status));

        List<Object[]> rows = relationships.dependencyEdges(PageRequest.of(0, GRAPH_EDGES + 1));
        boolean truncated = rows.size() > GRAPH_EDGES;
        List<Object[]> shown = truncated ? rows.subList(0, GRAPH_EDGES) : rows;
        Map<UUID, DocumentationArtifact> docs = new LinkedHashMap<>();
        shown.forEach((row) -> docs.putIfAbsent((UUID) row[0], null));
        artifacts.findAllById(docs.keySet()).forEach((artifact) -> docs.put(artifact.getId(), artifact));
        Map<String, GraphNode> nodes = new LinkedHashMap<>();
        List<GraphEdge> edges = new ArrayList<>();
        for (Object[] row : shown) {
            UUID documentId = (UUID) row[0];
            String path = (String) row[1];
            DocumentationArtifact artifact = docs.get(documentId);
            String from = "doc:" + documentId;
            String to = "file:" + path;
            nodes.putIfAbsent(from, new GraphNode(from, "document", artifact == null ? documentId.toString() : title(artifact)));
            nodes.putIfAbsent(to, new GraphNode(to, "file", path));
            edges.add(new GraphEdge(from, to, ((Number) row[2]).longValue()));
        }
        return new Health(Instant.now(), counts, repoStatus, workflowStatus, List.copyOf(nodes.values()), edges, truncated);
    }

    static String title(DocumentationArtifact artifact) {
        String markdown = artifact.getMarkdown();
        if (markdown != null) {
            for (String line : markdown.split("\\R", 40)) {
                String trimmed = line.strip();
                if (trimmed.startsWith("#")) {
                    String heading = trimmed.replaceFirst("^#+\\s*", "").strip();
                    if (!heading.isEmpty()) return heading.length() > 120 ? heading.substring(0, 120) : heading;
                }
            }
        }
        return "Document " + artifact.getId().toString().substring(0, 8);
    }
}
