package com.livingdocs.github.change;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.sync.AnalysisInput;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** LD-120: gọi Code Analyzer (POST /api/v1/analyze-repo) để lấy code entity và khoảng dòng của chúng. */
@Component
public class CodeAnalyzerClient {

    private final RestClient analyzerClient;

    public CodeAnalyzerClient(@Qualifier("codeAnalyzerRestClient") RestClient analyzerClient) {
        this.analyzerClient = analyzerClient;
    }

    /**
     * Entity của từng file, theo đường dẫn. File mà analyzer không phân tích được (status khác "ok")
     * không có trong kết quả.
     */
    public Map<String, List<CodeEntity>> analyze(String target, List<AnalysisInput.FileInput> files) {
        if (files.isEmpty()) {
            return Map.of();
        }
        JsonNode response;
        try {
            response = analyzerClient.post()
                    .uri("/api/v1/analyze-repo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new AnalysisInput("file", target, files))
                    .retrieve()
                    .body(JsonNode.class);
        } catch (RestClientException e) {
            throw new SourceChangeException("ANALYZER_UNAVAILABLE", "The code analyzer could not analyze the changed files.");
        }
        if (response == null || !response.path("files").isArray()) {
            throw new SourceChangeException("ANALYZER_UNAVAILABLE", "The code analyzer returned an invalid response.");
        }
        Map<String, List<CodeEntity>> result = new HashMap<>();
        for (JsonNode file : response.path("files")) {
            if ("ok".equals(file.path("status").asText())) {
                result.put(file.path("path").asText(), entities(file));
            }
        }
        return result;
    }

    /** Class (theo kind của analyzer), method "Class.method", function và endpoint "GET /path". */
    static List<CodeEntity> entities(JsonNode file) {
        List<CodeEntity> entities = new ArrayList<>();
        for (JsonNode cls : file.path("classes")) {
            String className = cls.path("name").asText();
            add(entities, cls.path("kind").asText("class").toUpperCase(Locale.ROOT), className, cls);
            for (JsonNode method : cls.path("methods")) {
                add(entities, "METHOD", className + "." + method.path("name").asText(), method);
            }
        }
        for (JsonNode function : file.path("functions")) {
            add(entities, "FUNCTION", function.path("name").asText(), function);
        }
        for (JsonNode endpoint : file.path("endpoints")) {
            add(entities, "ENDPOINT", endpoint.path("http_method").asText() + " " + endpoint.path("path").asText(), endpoint);
        }
        return entities;
    }

    /** Entity không có khoảng dòng thì không so được với diff nên bỏ qua. */
    private static void add(List<CodeEntity> entities, String kind, String name, JsonNode node) {
        if (node.path("lineno").isInt() && node.path("end_lineno").isInt()) {
            entities.add(new CodeEntity(kind, name, node.path("lineno").asInt(), node.path("end_lineno").asInt()));
        }
    }
}



