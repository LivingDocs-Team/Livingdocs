package com.livingdocs.github.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.livingdocs.github.dto.DocumentationGenerationRequest;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.UUID;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

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

    /** Analyze the latest authorized repository snapshot and start an AI documentation job. */
    public JsonNode generate(String userId, UUID repositoryId,
            DocumentationGenerationRequest request) {
        RepositorySnapshot snapshot = repositorySyncService.latest(userId, repositoryId);
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
