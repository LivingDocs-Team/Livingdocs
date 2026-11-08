package com.livingdocs.github.service;

import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.livingdocs.github.dto.DocumentationGenerationRequest;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.RepositorySnapshot;
import com.livingdocs.github.sync.RepositorySyncException;
import com.livingdocs.github.sync.SyncOptions;


@Service
public class DocumentationGenerationService {

    private final RepositorySyncService repositorySyncService;
    private final RestClient analyzerClient;
    private final RestClient aiServiceClient;
    private final ConcurrentMap<String, String> jobOwners = new ConcurrentHashMap<>();

    public DocumentationGenerationService(
            RepositorySyncService repositorySyncService,
            @Qualifier("codeAnalyzerRestClient") RestClient analyzerClient,
            @Qualifier("aiServiceRestClient") RestClient aiServiceClient) {
        this.repositorySyncService = repositorySyncService;
        this.analyzerClient = analyzerClient;
        this.aiServiceClient = aiServiceClient;
    }

    /**
     * Analyze the latest authorized repository snapshot and start an AI documentation job.
     * The snapshot is kept in memory only: after a restart the repository is synchronized again (LD-77).
     */
    public JsonNode generate(String userId, UUID repositoryId,
            DocumentationGenerationRequest request) {
        RepositorySnapshot snapshot = repositorySyncService.latestOrSync(userId, repositoryId);
        AnalysisInput input = AnalysisInput.from(snapshot);
        if (input.files().isEmpty()) {
            throw ApiException.badRequest("The latest repository sync contains no source files with content.");
        }

        JsonNode analysis;
        try {
            ResponseEntity<JsonNode> response = analyzerClient.post()
                    .uri("/api/v1/analyze-repo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(input)
                    .retrieve()
                    .toEntity(JsonNode.class);
            if (response.getStatusCode().value() != 200) {
                throw integrationFailure("ANALYZER_INVALID_RESPONSE",
                        "The code analyzer returned an unexpected HTTP status.");
            }
            analysis = response.getBody();
        } catch (RestClientException e) {
            throw integrationFailure("ANALYZER_FAILED",
                    "The code analyzer could not analyze the synchronized repository.");
        }

        if (analysis == null || !analysis.isObject() || !analysis.path("files").isArray()
                || analysis.path("files").isEmpty()) {
            throw integrationFailure("ANALYZER_INVALID_RESPONSE",
                    "The code analyzer returned an invalid or empty analysis response.");
        }

        ObjectNode generationRequest = (ObjectNode) analysis.deepCopy();
        if (request != null && request.templateId() != null && !request.templateId().isBlank()) {
            generationRequest.put("template_id", request.templateId());
        }
        if (request != null && request.outputLanguage() != null && !request.outputLanguage().isBlank()) {
            generationRequest.put("output_language", request.outputLanguage());
        }
        ObjectNode sourceSnapshot = generationRequest.putObject("source_snapshot");

        sourceSnapshot.put("repository_id", repositoryId.toString());
        sourceSnapshot.put("repository_full_name", snapshot.repository().fullName());
        sourceSnapshot.put("branch", snapshot.branch());
        sourceSnapshot.put("commit_sha", snapshot.headCommit().sha());
        sourceSnapshot.put("fetched_at", snapshot.fetchedAt().toString());
        JsonNode job;
        try {
            ResponseEntity<JsonNode> response = aiServiceClient.post()
                    .uri("/generate")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(generationRequest)
                    .retrieve()
                    .toEntity(JsonNode.class);
            if (response.getStatusCode().value() != 202) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                        "The AI service returned an unexpected HTTP status.");
            }
            job = response.getBody();
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "TEMPLATE_NOT_FOUND",
                        "The selected documentation template does not exist. Choose another template.");
            }
            if (e.getStatusCode().value() == 422) {
                String detail = DocumentationTemplateService.detail(e);
                throw new ApiException(HttpStatus.BAD_REQUEST, "GENERATION_REQUEST_INVALID",
                        detail != null ? detail : "The documentation generation settings are not valid.");
            }
            throw integrationFailure("AI_SERVICE_FAILED",
                    "The AI service could not start documentation generation.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED",
                    "The AI service could not start documentation generation.");
        }

        if (job == null || !job.isObject() || !job.path("id").isTextual()
                || !job.path("status").isTextual()) {
            throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                    "The AI service returned an invalid job response.");
        }
        jobOwners.put(job.path("id").asText(), userId);
        return job;
    }

    public JsonNode getJob(String userId, String jobId) {
        requireJobOwner(userId, jobId);
        return getAiJson("/jobs/" + jobId, "AI_SERVICE_FAILED",
                "The AI service could not return the documentation job.");
    }

    public String getResult(String userId, String jobId) {
        requireJobOwner(userId, jobId);
        try {
            String result = aiServiceClient.get().uri("/jobs/{id}/result", jobId)
                    .retrieve().body(String.class);
            if (result == null || result.isBlank()) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                        "The AI service returned an empty documentation result.");
            }
            return result;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw ApiException.notFound("Documentation job or result not found in the AI service.");
            }
            if (e.getStatusCode().value() == 409) {
                throw new ApiException(HttpStatus.CONFLICT, "DOCUMENTATION_NOT_READY",
                        "The documentation result is not ready yet.");
            }
            throw integrationFailure("AI_SERVICE_FAILED",
                    "The AI service could not return the generated documentation.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED",
                    "The AI service could not return the generated documentation.");
        }
    }

    public JsonNode getReport(String userId, String jobId) {
        requireJobOwner(userId, jobId);
        return getAiJson("/jobs/" + jobId + "/report", "AI_SERVICE_FAILED",
                "The AI service could not return the documentation report.");
    }

    public JsonNode saveOwnedDocument(String userId, java.util.Set<String> authorities,
            String jobId, String title) {
        if (authorities == null || !authorities.contains("DOCUMENT_CREATE")) {
            throw ApiException.forbidden("Missing permission: DOCUMENT_CREATE");
        }
        requireJobOwner(userId, jobId);
        try {
            JsonNode document = aiServiceClient.post().uri("/internal/documents/from-job")
                    .header("X-User-Id", userId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(java.util.Map.of("job_id", jobId, "title", title == null ? "" : title))
                    .retrieve().body(JsonNode.class);
            if (document == null || !document.path("id").isTextual()
                    || !userId.equals(document.path("owner_user_id").asText())) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                        "The AI service did not return a document owned by the authenticated user.");
            }
            return document;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) throw ApiException.notFound("Documentation job not found.");
            if (e.getStatusCode().value() == 409) throw new ApiException(HttpStatus.CONFLICT,
                    "DOCUMENTATION_NOT_READY", "The documentation job is not complete yet.");
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not save the document.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not save the document.");
        }
    }

    public JsonNode getDocument(String userId, String documentId) {
        try {
            JsonNode document = aiServiceClient.get().uri("/internal/documents/{id}", documentId)
                    .header("X-User-Id", userId).retrieve().body(JsonNode.class);
            if (document == null || !document.isObject()) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid document.");
            }
            return document;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) throw ApiException.notFound("Document not found.");
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return the document.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return the document.");
        }
    }

    public String getDocumentContent(String userId, String documentId, int version) {
        try {
            String content = aiServiceClient.get().uri(uri -> uri.path("/internal/documents/{id}/content")
                            .queryParam("version", version).build(documentId))
                    .header("X-User-Id", userId).retrieve().body(String.class);
            if (content == null) throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned no document content.");
            return content;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) throw ApiException.notFound("Document version not found.");
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return document content.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return document content.");
        }
    }
    public JsonNode getDocumentReviewEvidence(String userId, String documentId, int version) {
        try {
            JsonNode evidence = aiServiceClient.get()
                    .uri(uri -> uri.path("/internal/documents/{id}/review-evidence")
                            .queryParam("version", version)
                            .build(documentId))
                    .header("X-User-Id", userId)
                    .retrieve()
                    .body(JsonNode.class);

            if (evidence == null || !evidence.isObject()) {
                throw integrationFailure(
                        "AI_SERVICE_INVALID_RESPONSE",
                        "The AI service returned invalid review evidence.");
            }

            return evidence;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw ApiException.notFound("Review evidence not found for this document version.");
            }

            throw integrationFailure(
                    "AI_SERVICE_FAILED",
                    "The AI service could not return document review evidence.");
        } catch (RestClientException e) {
            throw integrationFailure(
                    "AI_SERVICE_FAILED",
                    "The AI service could not return document review evidence.");
        }
    }
    /**
 * Verify whether the repository source has changed since the document
 * version was generated.
 *
 * A fresh GitHub synchronization is required; cached snapshots must not
 * be used for this verification.
 */
public JsonNode verifySourceSnapshot(String ownerUserId, JsonNode evidence) {
    ObjectNode result = evidence.deepCopy();
    ObjectNode verification = JsonNodeFactory.instance.objectNode();

    verification.put("checked_at", Instant.now().toString());

    JsonNode sourceSnapshot = evidence.path("source_snapshot");
    String repositoryId = sourceSnapshot.path("repository_id").asText("");
    String expectedSha = sourceSnapshot.path("commit_sha").asText("");

    verification.put("expected_commit_sha", expectedSha);

    if (repositoryId.isBlank() || !expectedSha.matches("(?i)[0-9a-f]{40}")) {
        verification.put("status", "UNVERIFIABLE");
        verification.put("current_commit_sha", (String) null);
        verification.put("message", "The original source snapshot is missing or invalid.");
        result.set("source_verification", verification);
        return result;
    }

    final UUID parsedRepositoryId;
    try {
        parsedRepositoryId = UUID.fromString(repositoryId);
    } catch (IllegalArgumentException e) {
        verification.put("status", "UNVERIFIABLE");
        verification.put("current_commit_sha", (String) null);
        verification.put("message", "The original repository identifier is invalid.");
        result.set("source_verification", verification);
        return result;
    }

    try {
        RepositorySnapshot currentSnapshot = repositorySyncService.sync(
                ownerUserId,
                parsedRepositoryId,
                SyncOptions.defaults());

        String currentSha = currentSnapshot == null || currentSnapshot.headCommit() == null
                ? null
                : currentSnapshot.headCommit().sha();

        if (currentSha == null || !currentSha.matches("(?i)[0-9a-f]{40}")) {
            verification.put("status", "UNVERIFIABLE");
            verification.put("current_commit_sha", (String) null);
            verification.put("message", "The current repository snapshot has no valid commit SHA.");
        } else {
            verification.put("current_commit_sha", currentSha);

            if (expectedSha.equalsIgnoreCase(currentSha)) {
                verification.put("status", "MATCH");
                verification.put("message", "The repository source has not changed.");
            } else {
                verification.put("status", "CHANGED");
                verification.put("message", "The repository source has changed since document generation.");
            }
        }
    } catch (RepositorySyncException | ApiException e) {
        verification.put("status", "UNVERIFIABLE");
        verification.put("current_commit_sha", (String) null);
        verification.put("message", "The current repository source could not be verified.");
    }

    result.set("source_verification", verification);
    return result;
}
    public JsonNode getDocumentReviewComparison(String userId, String documentId) {
    try {
        JsonNode comparison = aiServiceClient.get()
                .uri("/internal/documents/{id}/review-comparison", documentId)
                .header("X-User-Id", userId)
                .retrieve()
                .body(JsonNode.class);

        if (comparison == null || !comparison.isObject()
                || !comparison.path("pending_version").isObject()) {
            throw integrationFailure(
                    "AI_SERVICE_INVALID_RESPONSE",
                    "The AI service returned invalid review comparison.");
        }

        return comparison;
    } catch (RestClientResponseException e) {
        if (e.getStatusCode().value() == 404) {
            throw ApiException.notFound("Document not found.");
        }
        if (e.getStatusCode().value() == 409) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "DOCUMENT_VERSION_NOT_PENDING",
                    "No document version is awaiting review.");
        }

        throw integrationFailure(
                "AI_SERVICE_FAILED",
                "The AI service could not return document version comparison.");
    } catch (RestClientException e) {
        throw integrationFailure(
                "AI_SERVICE_FAILED",
                "The AI service could not return document version comparison.");
    }
}

    public JsonNode editOwnedDocument(String userId, String documentId, int expectedVersion,
            String content, String note) {
        try {
            ObjectNode request = JsonNodeFactory.instance.objectNode().put("content", content)
                    .put("expected_version", expectedVersion);
            if (note != null) request.put("note", note);
            JsonNode version = aiServiceClient.put().uri("/internal/documents/{id}/content", documentId)
                    .header("X-User-Id", userId).contentType(MediaType.APPLICATION_JSON)
                    .body(request).retrieve().body(JsonNode.class);
            if (version == null || !version.isObject()) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid version.");
            }
            return version;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) throw ApiException.notFound("Owned document not found.");
            if (e.getStatusCode().value() == 409) throw new ApiException(HttpStatus.CONFLICT,
                    "DOCUMENT_VERSION_PENDING", "A document version is already awaiting review.");
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not save the edited version.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not save the edited version.");
        }
    }

    public void resolveDocumentVersion(String actorUserId, String ownerUserId, String documentId,
            int version, String decision, String note) {
        try {
            ObjectNode request = JsonNodeFactory.instance.objectNode()
                    .put("version", version).put("decision", decision);
            if (note != null) request.put("note", note);
            aiServiceClient.post().uri("/internal/documents/{id}/review-decision", documentId)
                    .header("X-User-Id", actorUserId)
                    .header("X-Document-Owner-Id", ownerUserId)
                    .contentType(MediaType.APPLICATION_JSON).body(request)
                    .retrieve().toBodilessEntity();
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) throw ApiException.notFound("Owned document version not found.");
            if (e.getStatusCode().value() == 409) throw new ApiException(HttpStatus.CONFLICT,
                    "DOCUMENT_VERSION_CONFLICT", "The document version changed during review.");
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not record the document decision.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not record the document decision.");
        }
    }

    private JsonNode getAiJson(String path, String code, String message) {
        try {
            JsonNode result = aiServiceClient.get().uri(path).retrieve().body(JsonNode.class);
            if (result == null || !result.isObject()) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                        "The AI service returned an invalid response.");
            }
            return result;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw ApiException.notFound("Documentation job or report not found in the AI service.");
            }
            if (e.getStatusCode().value() == 409) {
                throw new ApiException(HttpStatus.CONFLICT, "DOCUMENTATION_NOT_READY",
                        "The documentation job or report is not ready yet.");
            }
            throw integrationFailure(code, message);
        } catch (RestClientException e) {
            throw integrationFailure(code, message);
        }
    }

    private void requireJobOwner(String userId, String jobId) {
        String owner = jobOwners.get(jobId);
        if (owner == null) {
            throw ApiException.notFound("Documentation job not found or the service was restarted.");
        }
        if (!Objects.equals(owner, userId)) {
            throw ApiException.forbidden("This documentation job belongs to another user.");
        }
    }

    private ApiException integrationFailure(String code, String message) {
        return new ApiException(HttpStatus.BAD_GATEWAY, code, message);
    }
}
