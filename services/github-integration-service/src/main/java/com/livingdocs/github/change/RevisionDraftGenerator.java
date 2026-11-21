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
import org.springframework.web.client.RestClientException;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

@Component
public class RevisionDraftGenerator {
    private final RestClient analyzer;
    private final RestClient ai;
    private final RestClient revisionAi;
    private final SourceChangeService source;
    private final ConnectedRepositoryRepository repositories;
    private final DocumentWorkflowService workflows;
    private final RevisionJobQueue jobs;
    private final TransactionTemplate transaction;

    public RevisionDraftGenerator(@Qualifier("codeAnalyzerRestClient") RestClient analyzer,
            @Qualifier("aiServiceRestClient") RestClient ai,
            @Qualifier("revisionAiRestClient") RestClient revisionAi, SourceChangeService source,
            ConnectedRepositoryRepository repositories, DocumentWorkflowService workflows,
            RevisionJobQueue jobs, PlatformTransactionManager manager) {
        this.analyzer = analyzer;
        this.ai = ai;
        this.revisionAi = revisionAi;
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
        var revision = source.draftSource(repo, request, change.getId());
        if (revision.operations().isEmpty()) {
            return;
        }
        var analyzedFiles = JsonNodeFactory.instance.arrayNode();
        if (!revision.files().isEmpty()) {
            JsonNode analysis = analyzer.post().uri("/api/v1/analyze-repo")
                    .body(new AnalysisInput("repository", repo.getFullName(), revision.files()))
                    .retrieve().body(JsonNode.class);
            if (analysis == null || !analysis.path("files").isArray()) {
                throw new SourceChangeException("ANALYZER_UNAVAILABLE", "Missing source analysis for revision draft.");
            }
            var paths = StreamSupport.stream(analysis.path("files").spliterator(), false)
                    .map(file -> file.path("path").asText()).collect(Collectors.toSet());
            var expected = revision.files().stream().map(AnalysisInput.FileInput::path).collect(Collectors.toSet());
            if (!paths.equals(expected) || analysis.path("files").size() != expected.size()) {
                throw new SourceChangeException("ANALYZER_UNAVAILABLE", "Incomplete source analysis for revision draft.");
            }
            analysis.path("files").forEach(analyzedFiles::add);
        }

        for (JsonNode candidate : candidates) {
            String id = candidate.path("id").asText();
            if (!workflows.acceptsRevisionDraft(id)) {
                continue;
            }
            String owner = candidate.path("owner_user_id").asText();
            ObjectNode body = JsonNodeFactory.instance.objectNode();
            body.put("source_change_id", change.getId().toString());
            body.put("trigger", request.trigger().name());
            body.put("pull_request_number", request.pullRequestNumber());
            body.put("base_version", candidate.path("current_version").asInt());
            var paths = new HashSet<String>();
            var operations = body.putArray("file_changes");
            for (var file : revision.operations()) {
                if (file.documentId() != null && (!id.equals(file.documentId())
                        || !Objects.equals(file.documentVersion(), candidate.path("current_version").asInt()))) {
                    continue;
                }
                var entry = operations.addObject().put("path", file.path()).put("action", file.action());
                entry.put("previous_path", file.previousPath());
                entry.put("blob_sha", file.blobSha());
                if (file.blobSha() != null) {
                    paths.add(file.path());
                }
            }
            if (operations.isEmpty()) {
                continue;
            }
            if (operations.size() > 50) {
                throw new SourceChangeException("DRAFT_FILE_LIMIT_EXCEEDED", "Too many source operations for one draft.");
            }
            var files = body.putArray("files");
            analyzedFiles.forEach(file -> {
                if (paths.contains(file.path("path").asText())) {
                    files.add(file);
                }
            });
            ObjectNode snapshot = body.putObject("source_snapshot");
            snapshot.put("repository_id", repo.getId().toString());
            snapshot.put("repository_full_name", repo.getFullName());
            snapshot.put("branch", revision.branch());
            snapshot.put("commit_sha", request.commitSha());
            snapshot.put("fetched_at", Instant.now().toString());
            snapshot.put("pull_request_number", request.pullRequestNumber());
            snapshot.put("pull_request_base_sha", revision.pullRequestBaseSha());

            JsonNode prepared = callDraft(revisionAi, "prepare", id, owner, body);
            if (prepared == null || prepared.isNull()) {
                continue;
            }
            var deadline = jobs.renew(lease, OffsetDateTime.now(ZoneOffset.UTC)).orElseThrow(
                    () -> new SourceChangeException("LEASE_EXPIRED", "Revision job lease is no longer current."));
            transaction.executeWithoutResult(status -> workflows.submitRevisionDraft(candidate, request, () -> {
                var connected = repositories.lockById(request.repositoryId());
                if (connected.isEmpty()) {
                    return null;
                }
                if (!Objects.equals(revision.pullRequestBaseSha(),
                        source.requireCurrentRevision(connected.get(), request))) {
                    throw new SourceChangeException("PULL_REQUEST_BASE_CHANGED", "The pull request base changed.");
                }
                if (!jobs.lockCurrentLease(lease, OffsetDateTime.now(ZoneOffset.UTC), deadline)) {
                    throw new SourceChangeException("LEASE_EXPIRED", "Revision job lease is no longer current.");
                }
                body.set("prepared", prepared);
                body.put("lease_expires_at", deadline.toString());
                return callDraft(ai, "commit", id, owner, body);
            }));
        }
    }

    private JsonNode callDraft(RestClient client, String action, String id, String owner, ObjectNode body) {
        try {
            return client.post().uri("/internal/documents/{id}/revision-drafts/" + action, id)
                    .header("X-User-Id", owner).body(body).retrieve().body(JsonNode.class);
        } catch (RestClientResponseException exception) {
            if ("commit".equals(action) && exception.getStatusCode().is5xxServerError()) {
                throw new SourceChangeException("DRAFT_COMMIT_UNCERTAIN", "The AI draft commit response was lost.");
            }
            if (exception.getStatusCode().value() == 409) {
                throw new SourceChangeException("DRAFT_VERSION_CONFLICT", "The document changed during drafting.");
            }
            throw new SourceChangeException("AI_SERVICE_UNAVAILABLE", "Could not generate a grounded revision draft.");
        } catch (RestClientException exception) {
            if ("commit".equals(action)) {
                throw new SourceChangeException("DRAFT_COMMIT_UNCERTAIN", "The AI draft commit response was lost.");
            }
            throw new SourceChangeException("AI_SERVICE_UNAVAILABLE", "Could not generate a grounded revision draft.");
        }
    }
}
