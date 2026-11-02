package com.livingdocs.github.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationTemplateRequest;
import com.livingdocs.github.exception.ApiException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

/** Documentation templates are managed by the AI service; this service forwards the requests. */
@Service
public class DocumentationTemplateService {

    private final RestClient aiServiceClient;

    public DocumentationTemplateService(@Qualifier("aiServiceRestClient") RestClient aiServiceClient) {
        this.aiServiceClient = aiServiceClient;
    }

    public JsonNode list() {
        return call(() -> aiServiceClient.get().uri("/templates").retrieve().body(JsonNode.class),
                true);
    }

    public JsonNode sections() {
        return call(() -> aiServiceClient.get().uri("/templates/sections").retrieve()
                .body(JsonNode.class), false);
    }

    public JsonNode get(String templateId) {
        return call(() -> aiServiceClient.get().uri("/templates/{id}", templateId).retrieve()
                .body(JsonNode.class), false);
    }

    public JsonNode create(DocumentationTemplateRequest request) {
        return call(() -> aiServiceClient.post().uri("/templates")
                .contentType(MediaType.APPLICATION_JSON).body(body(request))
                .retrieve().body(JsonNode.class), false);
    }

    public JsonNode update(String templateId, DocumentationTemplateRequest request) {
        return call(() -> aiServiceClient.put().uri("/templates/{id}", templateId)
                .contentType(MediaType.APPLICATION_JSON).body(body(request))
                .retrieve().body(JsonNode.class), false);
    }

    public void delete(String templateId) {
        call(() -> {
            aiServiceClient.delete().uri("/templates/{id}", templateId).retrieve().toBodilessEntity();
            return null;
        }, null);
    }

    private static DocumentationTemplateRequest body(DocumentationTemplateRequest request) {
        if (request == null) {
            throw ApiException.badRequest("A template body is required.");
        }
        return request;
    }

    /** expectArray: true = an array, false = an object, null = no body expected. */
    private JsonNode call(Supplier<JsonNode> request, Boolean expectArray) {
        JsonNode result;
        try {
            result = request.get();
        } catch (RestClientResponseException e) {
            throw mapError(e);
        } catch (RestClientException e) {
            throw unavailable();
        }
        if (expectArray != null && (result == null
                || (expectArray ? !result.isArray() : !result.isObject()))) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_INVALID_RESPONSE",
                    "The AI service returned an invalid template response.");
        }
        return result;
    }

    private ApiException mapError(RestClientResponseException e) {
        String detail = detail(e);
        return switch (e.getStatusCode().value()) {
            case 404 -> new ApiException(HttpStatus.NOT_FOUND, "TEMPLATE_NOT_FOUND",
                    "Documentation template not found.");
            case 403 -> new ApiException(HttpStatus.FORBIDDEN, "TEMPLATE_READ_ONLY",
                    "Built-in templates cannot be changed or deleted.");
            case 409 -> new ApiException(HttpStatus.CONFLICT, "TEMPLATE_NAME_TAKEN",
                    detail != null ? detail : "A template with this name already exists.");
            case 400, 422 -> new ApiException(HttpStatus.BAD_REQUEST, "TEMPLATE_INVALID",
                    detail != null ? detail : "The template is not valid.");
            default -> unavailable();
        };
    }

    private static ApiException unavailable() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "AI_SERVICE_FAILED",
                "The AI service could not process the template request.");
    }

    /**
     * Readable reason from the AI service: {"detail": "text"} or FastAPI's validation list
     * {"detail": [{"loc": ["body", "sections"], "msg": "..."}]}. Contains no credentials.
     */
    static String detail(RestClientResponseException e) {
        JsonNode body;
        try {
            body = e.getResponseBodyAs(JsonNode.class);
        } catch (RuntimeException ignored) {
            return null;
        }
        if (body == null) return null;
        JsonNode detail = body.path("detail");
        if (detail.isTextual()) return detail.asText();
        if (!detail.isArray()) return null;
        List<String> parts = new ArrayList<>();
        for (JsonNode item : detail) {
            JsonNode loc = item.path("loc");
            String field = loc.isArray() && !loc.isEmpty() ? loc.get(loc.size() - 1).asText() : "";
            String msg = item.path("msg").asText("");
            parts.add(field.isEmpty() ? msg : field + ": " + msg);
        }
        return parts.isEmpty() ? null : String.join("; ", parts);
    }
}
