package com.livingdocs.github.change;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.service.DocumentWorkflowService;
import com.livingdocs.github.service.SourceChangeService;
import com.livingdocs.github.sync.AnalysisInput;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Objects;

@Component
public class RevisionDraftGenerator {
    private final RestClient analyzer;
    private final RestClient ai;
    private final SourceChangeService source;
    private final ConnectedRepositoryRepository repositories;
    private final DocumentWorkflowService workflows;
    private final RevisionJobQueue jobs;
    private final TransactionTemplate transaction;

    public RevisionDraftGenerator(@Qualifier("codeAnalyzerRestClient") RestClient analyzer,
            @Qualifier("aiServiceRestClient") RestClient ai, SourceChangeService source,
            ConnectedRepositoryRepository repositories, DocumentWorkflowService workflows,
            RevisionJobQueue jobs, PlatformTransactionManager manager) {
        this.analyzer = analyzer;
        this.ai = ai;
        this.source = source;
        this.repositories = repositories;
        this.workflows = workflows;
        this.jobs = jobs;
        this.transaction = new TransactionTemplate(manager);
    }

    public void generate(RevisionJobQueue.Lease lease, SourceChange change) {
        SourceChangeRequest request = lease.request();
        var repo = repositories.findById(request.repositoryId()).orElse(null);
        if (repo == null) {
            return;
        }
        JsonNode candidates = ai.get().uri("/internal/revision-draft-candidates/{id}", repo.getId())
                .retrieve().body(JsonNode.class);
        if (candidates == null || !candidates.isArray()) {
            throw new SourceChangeException("AI_SERVICE_UNAVAILABLE", "Invalid revision draft candidates.");
        }
        if (candidates.isEmpty()) {
            return;
        }
        var revision = source.draftSource(repo, request);
        if (revision.files().isEmpty()) {
            return;
        }
        JsonNode analysis = analyzer.post().uri("/api/v1/analyze-repo")
                .body(new AnalysisInput("repository", repo.getFullName(), revision.files()))
                .retrieve().body(JsonNode.class);
        if (analysis == null || !analysis.path("files").isArray() || analysis.path("files").isEmpty()) {
            throw new SourceChangeException("ANALYZER_UNAVAILABLE", "Missing source analysis for revision draft.");
        }

        for (JsonNode candidate : candidates) {
            transaction.executeWithoutResult(status -> workflows.submitRevisionDraft(candidate, request, () -> {
                var connected = repositories.lockById(request.repositoryId());
                if (connected.isEmpty() || !jobs.lockCurrentLease(lease, OffsetDateTime.now(ZoneOffset.UTC))) {
                    return null;
                }
                if (!Objects.equals(revision.pullRequestBaseSha(),
                        source.requireCurrentRevision(connected.get(), request))) {
                    throw new SourceChangeException("PULL_REQUEST_BASE_CHANGED", "The pull request base changed.");
                }
                ObjectNode body = JsonNodeFactory.instance.objectNode();
                body.put("source_change_id", change.getId().toString());
                body.put("trigger", request.trigger().name());
                body.put("pull_request_number", request.pullRequestNumber());
                body.put("base_version", candidate.path("current_version").asInt());
                body.set("files", analysis.path("files"));
                ObjectNode snapshot = body.putObject("source_snapshot");
                snapshot.put("repository_id", repo.getId().toString());
                snapshot.put("repository_full_name", repo.getFullName());
                snapshot.put("branch", revision.branch());
                snapshot.put("commit_sha", request.commitSha());
                snapshot.put("fetched_at", Instant.now().toString());
                snapshot.put("pull_request_number", request.pullRequestNumber());
                snapshot.put("pull_request_base_sha", revision.pullRequestBaseSha());
                String id = candidate.path("id").asText();
                String owner = candidate.path("owner_user_id").asText();
                return createDraft(id, owner, body);
            }));
        }
    }

    private JsonNode createDraft(String id, String owner, ObjectNode body) {
        try {
            return ai.post().uri("/internal/documents/{id}/revision-drafts", id)
                    .header("X-User-Id", owner).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientResponseException exception) {
            if (exception.getStatusCode().value() == 409) {
                throw new SourceChangeException("DRAFT_VERSION_CONFLICT", "The document changed during drafting.");
            }
            throw new SourceChangeException("AI_SERVICE_UNAVAILABLE", "Could not generate a grounded revision draft.");
        }
    }
}
