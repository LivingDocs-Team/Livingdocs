package com.livingdocs.github.change;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.util.ArrayList;
import java.util.List;

/**
 * LD-122: hỏi ai-service phần tài liệu đã lưu nào có thể đã cũ vì một source change
 * (POST /internal/affected-documents, cùng luật so khớp với LD-148).
 * Chỉ gửi tài liệu của chính repo (target = owner/name), giống phân tích lệch tài liệu (LD-145).
 */
@Component
public class AffectedDocumentsClient {

    private final RestClient aiServiceClient;

    public AffectedDocumentsClient(@Qualifier("aiServiceRestClient") RestClient aiServiceClient) {
        this.aiServiceClient = aiServiceClient;
    }

    /** File của source change theo dạng LD-116; change: ADDED, MODIFIED, REMOVED, RENAMED. */
    public record ChangedFile(String path, @JsonProperty("previous_path") String previousPath, String change,
                              String language, List<ChangedEntity> entities) {
    }

    /** change: ADDED, MODIFIED, REMOVED. */
    public record ChangedEntity(String kind, String name, String change) {
    }

    /** Một phần tài liệu bị ảnh hưởng; dependency: direct hoặc dependent (LD-125). */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Affected(@JsonProperty("document_id") String documentId, String title, Integer version,
                           String path, @JsonProperty("documents_file") String documentsFile,
                           String dependency, List<String> reasons) {
    }

    private record Request(String repository, List<ChangedFile> files,
                           @JsonProperty("document_ids") List<String> documentIds) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record Result(List<Affected> documents) {
    }

    /** Repo chưa có tài liệu nào thì không hỏi tiếp. Lỗi ai-service: SourceChangeException AI_SERVICE_UNAVAILABLE. */
    public List<Affected> find(String repository, List<ChangedFile> files) {
        List<String> documentIds = documentIdsOf(repository);
        if (documentIds.isEmpty()) {
            return List.of();
        }
        Result result;
        try {
            result = aiServiceClient.post()
                    .uri("/internal/affected-documents")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new Request(repository, files, documentIds))
                    .retrieve()
                    .body(Result.class);
        } catch (RestClientException e) {
            throw unavailable();
        }
        if (result == null || result.documents() == null) {
            throw unavailable();
        }
        return result.documents();
    }

    private List<String> documentIdsOf(String repository) {
        JsonNode documents;
        try {
            documents = aiServiceClient.get().uri("/documents").retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            throw unavailable();
        }
        if (documents == null || !documents.isArray()) {
            throw unavailable();
        }
        List<String> ids = new ArrayList<>();
        for (JsonNode document : documents) {
            if (repository.equalsIgnoreCase(document.path("target").asText()) && document.path("id").isTextual()) {
                ids.add(document.path("id").asText());
            }
        }
        return ids;
    }

    private static SourceChangeException unavailable() {
        return new SourceChangeException("AI_SERVICE_UNAVAILABLE",
                "The AI service could not check which documentation is affected.");
    }
}
