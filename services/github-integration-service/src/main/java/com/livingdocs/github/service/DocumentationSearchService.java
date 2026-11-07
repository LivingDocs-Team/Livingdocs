package com.livingdocs.github.service;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DocumentationSearchResponse;
import com.livingdocs.github.dto.DocumentationSearchResponse.SearchResult;
import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.RepositorySnapshot;

/** Searches analyzer documentation and symbols from the latest authorized repository snapshot. */
@Service
public class DocumentationSearchService {
    private static final int MAX_QUERY_LENGTH = 200;
    private static final int MAX_RESULTS = 50;
    private static final Pattern TOKEN_SPLIT = Pattern.compile("[^\\p{L}\\p{N}_]+", Pattern.UNICODE_CHARACTER_CLASS);

    private final RepositorySyncService syncService;
    private final RepositoryManagementService repositoryService;
    private final RestClient analyzerClient;
    private final Map<UUID, CachedAnalysis> cache = new ConcurrentHashMap<>();

    public DocumentationSearchService(RepositorySyncService syncService,
            RepositoryManagementService repositoryService,
            @Qualifier("codeAnalyzerRestClient") RestClient analyzerClient) {
        this.syncService = syncService;
        this.repositoryService = repositoryService;
        this.analyzerClient = analyzerClient;
    }

    public DocumentationSearchResponse search(String userId, java.util.UUID repositoryId, String rawQuery) {
        if (rawQuery == null || rawQuery.isBlank()) throw ApiException.badRequest("Search query is required.");
        String query = rawQuery.trim();
        if (query.length() > MAX_QUERY_LENGTH || query.codePoints().anyMatch(Character::isISOControl)) {
            throw ApiException.badRequest("Search query must be at most 200 characters and contain no control characters.");
        }

        RepositoryResponse repository = repositoryService.get(userId, repositoryId);
        RepositorySnapshot snapshot = syncService.latestOrSync(userId, repositoryId);
        String commit = snapshot.headCommit() == null ? "" : snapshot.headCommit().sha();
        CachedAnalysis cached = cache.compute(repositoryId, (ignored, current) ->
                current != null && current.commit().equals(commit) ? current
                        : new CachedAnalysis(commit, analyze(snapshot)));
        JsonNode analysis = cached.analysis();

        List<SearchResult> results = new ArrayList<>();
        JsonNode files = analysis.path("files");
        if (files.isArray()) {
            for (JsonNode file : files) {
                String path = text(file, "path", "");
                String language = text(file, "language", "");
                for (JsonNode clazz : iterable(file.path("classes"))) {
                    String title = text(clazz, "name", "Code entity");
                    String classSummary = text(clazz, "docstring", "");
                    addHits(results, query, repository, path, language, title, classSummary,
                            text(clazz, "kind", "class"), integer(clazz, "lineno"),
                            code(clazz, title), true);
                    for (JsonNode method : iterable(clazz.path("methods"))) {
                        String methodTitle = title + "." + text(method, "name", "member");
                        addHits(results, query, repository, path, language, methodTitle,
                                text(method, "docstring", ""), "method", integer(method, "lineno"),
                                code(method, methodTitle), true);
                    }
                }
                for (JsonNode function : iterable(file.path("functions"))) {
                    String title = text(function, "name", "Function");
                    addHits(results, query, repository, path, language, title,
                            text(function, "docstring", ""), "function", integer(function, "lineno"),
                            code(function, title), true);
                }
                for (JsonNode endpoint : iterable(file.path("endpoints"))) {
                    String title = text(endpoint, "http_method", "HTTP") + " " + text(endpoint, "path", "endpoint");
                    addHits(results, query, repository, path, language, title,
                            text(endpoint, "response", ""), "endpoint", integer(endpoint, "lineno"),
                            code(endpoint, title), true);
                }
            }
        }
        results.sort(Comparator.comparingInt(SearchResult::score).reversed()
                .thenComparing(SearchResult::path, String.CASE_INSENSITIVE_ORDER)
                .thenComparing(SearchResult::title, String.CASE_INSENSITIVE_ORDER));
        List<SearchResult> limited = results.stream().limit(MAX_RESULTS).toList();
        return new DocumentationSearchResponse(query, results.size(), limited);
    }

    private JsonNode analyze(RepositorySnapshot snapshot) {
        try {
            ResponseEntity<JsonNode> response = analyzerClient.post().uri("/api/v1/analyze-repo")
                    .contentType(MediaType.APPLICATION_JSON).body(AnalysisInput.from(snapshot))
                    .retrieve().toEntity(JsonNode.class);
            JsonNode body = response.getBody();
            if (!response.getStatusCode().is2xxSuccessful() || body == null || !body.path("files").isArray()) {
                throw new ApiException(HttpStatus.BAD_GATEWAY, "ANALYZER_INVALID_RESPONSE",
                        "The code analyzer returned an invalid search response.");
            }
            return body;
        } catch (RestClientException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "ANALYZER_FAILED",
                    "The code analyzer is unavailable for documentation search.");
        }
    }

    private static void addHits(List<SearchResult> hits, String query, RepositoryResponse repository,
            String path, String language, String title, String documentation, String entityType,
            Integer line, String codeText, boolean includeCode) {
        String docText = (title + " " + documentation + " " + path).trim();
        int docScore = score(query, docText);
        if (docScore > 0 && !documentation.isBlank()) {
            hits.add(new SearchResult("doc:" + path + ":" + title, "documentation", title,
                    documentation, repository.id(), repository.fullName(), path, language, line,
                    sourceUrl(repository.htmlUrl(), repository.defaultBranch(), path, line), docScore));
        }
        int codeScore = includeCode ? score(query, title + " " + entityType + " " + codeText + " " + path) : 0;
        if (codeScore > 0) {
            hits.add(new SearchResult("code:" + path + ":" + title, "code", title,
                    entityType + (codeText.isBlank() ? "" : " - " + codeText), repository.id(),
                    repository.fullName(), path, language, line,
                    sourceUrl(repository.htmlUrl(), repository.defaultBranch(), path, line), codeScore));
        }
    }

    private static int score(String query, String text) {
        String haystack = text.toLowerCase(Locale.ROOT);
        String normalizedQuery = query.toLowerCase(Locale.ROOT);
        if (haystack.contains(normalizedQuery)) return 100 + normalizedQuery.length();
        int score = 0;
        for (String token : TOKEN_SPLIT.split(normalizedQuery)) {
            if (!token.isBlank() && haystack.contains(token)) score += 10 + token.length();
        }
        return score;
    }

    private static String sourceUrl(String base, String branch, String path, Integer line) {
        if (base == null || base.isBlank() || path == null || path.isBlank()) return null;
        String encodedPath = java.util.Arrays.stream(path.split("/", -1))
                .map(part -> URLEncoder.encode(part, StandardCharsets.UTF_8).replace("+", "%20"))
                .collect(java.util.stream.Collectors.joining("/"));
        String ref = branch == null || branch.isBlank() ? "HEAD" : branch;
        String url = base.replaceAll("/$", "") + "/blob/" + URLEncoder.encode(ref, StandardCharsets.UTF_8)
                .replace("+", "%20").replace("%2F", "/") + "/" + encodedPath;
        return line == null ? url : url + "#L" + line;
    }

    private static String code(JsonNode node, String fallback) {
        String signature = text(node, "signature", "");
        String source = text(node, "source", "");
        return !signature.isBlank() ? signature : !source.isBlank() ? source.lines().findFirst().orElse(fallback) : fallback;
    }
    private static String text(JsonNode node, String field, String fallback) {
        JsonNode value = node.path(field);
        return value.isTextual() ? value.asText() : fallback;
    }
    private static Integer integer(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.canConvertToInt() ? value.asInt() : null;
    }
    private static Iterable<JsonNode> iterable(JsonNode node) {
        return node.isArray() ? node : List.of();
    }

    private record CachedAnalysis(String commit, JsonNode analysis) { }
}
