package com.livingdocs.github.service;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.client.GitHubPullRequestFile;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.LanguageDetector;

/**
 * LD-145 Documentation drift detection: phân tích thủ công một Pull Request.
 *
 * <pre>
 * GitHub: thông tin PR + file thay đổi (patch)          LD-146
 *       + nội dung file Python/Java ở merge base và head
 * code-analyzer: phân tích 2 phiên bản -> before / after
 * GitHub: các file Markdown của repo ở commit head (README, docs/...)
 * ai-service POST /drift/analyze                       LD-147 / LD-148 / LD-149
 *   -> findings (Referential / Signature / Semantic), tài liệu bị ảnh hưởng, bằng chứng
 * </pre>
 *
 * Lỗi khi tải nội dung một file hoặc khi gọi service phân tích không làm hỏng cả lần phân tích:
 * ai-service vẫn đọc thay đổi từ diff (độ tin cậy thấp hơn) và báo cáo có thêm cảnh báo.
 * Chỉ kiểm tra tài liệu đã lưu của chính repo này, không đụng tới tài liệu của repo khác.
 */
@Service
public class DriftAnalysisService {

    /** Số file Python/Java tối đa được tải nội dung và phân tích; các file còn lại chỉ dùng diff. */
    static final int MAX_ANALYZED_FILES = 100;
    static final long MAX_SOURCE_BYTES = 1_000_000;
    static final int MAX_REPOSITORY_DOCS = 30;
    /** Giới hạn của ai-service cho một tài liệu (ContextDocument.content). */
    static final int MAX_DOC_CHARS = 200_000;
    /** Giới hạn của ai-service cho patch của một file. */
    static final int MAX_PATCH_CHARS = 1_000_000;

    private static final Set<String> ANALYZED_LANGUAGES = Set.of("python", "java");
    private static final Set<String> SEVERITY_LEVELS = Set.of("low", "medium", "high", "critical");
    private static final Set<String> GITHUB_STATUSES = Set.of(
            "added", "modified", "removed", "renamed", "copied", "changed", "unchanged");
    private static final Set<String> SKIPPED_DIRECTORIES = Set.of(
            "node_modules", "target", "dist", "build", "vendor", ".venv", "venv", ".git");

    private final RepositorySyncService repositorySyncService;
    private final GitHubConnectionService connectionService;
    private final GitHubClient gitHubClient;
    private final RestClient analyzerClient;
    private final RestClient aiServiceClient;
    private final JsonNodeFactory json = JsonNodeFactory.instance;
    /** Báo cáo -> người tạo (giữ trong bộ nhớ như báo cáo của ai-service). */
    private final ConcurrentMap<String, String> reportOwners = new ConcurrentHashMap<>();

    public DriftAnalysisService(
            RepositorySyncService repositorySyncService,
            GitHubConnectionService connectionService,
            GitHubClient gitHubClient,
            @Qualifier("codeAnalyzerRestClient") RestClient analyzerClient,
            @Qualifier("aiServiceRestClient") RestClient aiServiceClient) {
        this.repositorySyncService = repositorySyncService;
        this.connectionService = connectionService;
        this.gitHubClient = gitHubClient;
        this.analyzerClient = analyzerClient;
        this.aiServiceClient = aiServiceClient;
    }

    // ------------------------------------------------------------------ analyze one Pull Request

    public JsonNode analyzePullRequest(String userId, UUID repositoryId, DriftAnalysisRequest request) {
        int number = requireNumber(request);
        ConnectedRepository repository = repositorySyncService.requireOwned(userId, repositoryId);
        GitHubConnection connection = connectionService.getActiveConnection(userId);
        Context ctx = new Context(repository.getFullName(), connection);

        GitHubPullRequest pr;
        List<GitHubPullRequestFile> files;
        try {
            pr = gitHubClient.getPullRequest(ctx.token(), ctx.owner, ctx.name, number);
            files = gitHubClient.listPullRequestFiles(ctx.token(), ctx.owner, ctx.name, number);
        } catch (GitHubApiException e) {
            throw translate(e, ctx, "Pull request #" + number + " was not found in " + ctx.fullName + ".",
                    "PULL_REQUEST_NOT_FOUND");
        }
        if (pr == null || pr.head() == null || pr.base() == null
                || pr.head().sha() == null || pr.base().sha() == null) {
            throw integrationFailure("GITHUB_INVALID_RESPONSE",
                    "GitHub returned an incomplete pull request.");
        }
        if (files == null || files.isEmpty()) {
            throw ApiException.badRequest("Pull request #" + number + " has no changed files.");
        }

        String baseSha = mergeBase(ctx, pr);
        Map<String, JsonNode> before = new HashMap<>();
        Map<String, JsonNode> after = new HashMap<>();
        analyzeSources(ctx, files, baseSha, pr.head().sha(), before, after);

        List<ObjectNode> docs = request.includeRepositoryDocs() == null || request.includeRepositoryDocs()
                ? repositoryDocs(ctx, pr.head().sha()) : List.of();
        List<String> documentIds = documentIds(ctx, request.documentIds());

        ObjectNode body = driftRequest(ctx, pr, number, baseSha, files, before, after, docs, documentIds);
        ObjectNode report = postDrift(body);
        ArrayNode warnings = json.arrayNode();             // warnings of this service first
        ctx.warnings.forEach(warnings::add);
        if (report.path("warnings").isArray()) {
            report.path("warnings").forEach(warnings::add);
        }
        report.set("warnings", warnings);
        reportOwners.put(report.path("id").asText(), userId);
        return report;
    }

    /** Báo cáo của một repo (mới nhất trước), chỉ những báo cáo người dùng này tạo. */
    public JsonNode listReports(String userId, UUID repositoryId, Integer pullRequestNumber) {
        ConnectedRepository repository = repositorySyncService.requireOwned(userId, repositoryId);
        if (pullRequestNumber != null && pullRequestNumber < 1) {
            throw ApiException.badRequest("pullRequest must be a positive number.");
        }
        JsonNode rows = getAiJson(pullRequestNumber == null
                        ? aiServiceClient.get().uri("/drift/reports?repository={r}", repository.getFullName())
                        : aiServiceClient.get().uri("/drift/reports?repository={r}&pull_request={n}",
                                repository.getFullName(), pullRequestNumber),
                "The AI service could not list drift reports.");
        if (!rows.isArray()) {
            throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid response.");
        }
        ArrayNode own = json.arrayNode();
        for (JsonNode row : rows) {
            if (Objects.equals(reportOwners.get(row.path("id").asText()), userId)) {
                own.add(row);
            }
        }
        return own;
    }

    public JsonNode getReport(String userId, String reportId) {
        return getReport(userId, null, reportId, null);
    }

    /**
     * LD-159: one report of a repository (the route the frontend reaches through the BFF).
     * {@code minSeverity} (low | medium | high | critical) keeps only findings at that level or above.
     */
    public JsonNode getReport(String userId, UUID repositoryId, String reportId, String minSeverity) {
        String repository = requireReport(userId, repositoryId, reportId);
        String level = severity(minSeverity);
        JsonNode report = getAiJson(level == null
                        ? aiServiceClient.get().uri("/drift/reports/{id}", reportId)
                        : aiServiceClient.get().uri("/drift/reports/{id}?min_severity={s}", reportId, level),
                "The AI service could not return the drift report.");
        if (!report.isObject()) {
            throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid response.");
        }
        if (repository != null && !repository.equalsIgnoreCase(report.path("repository").asText())) {
            throw ApiException.notFound("Drift report not found for this repository.");
        }
        return report;
    }

    /** LD-159: the report as Markdown grouped by severity (Pull Request comment, download). */
    public String getReportMarkdown(String userId, UUID repositoryId, String reportId, String minSeverity) {
        requireReport(userId, repositoryId, reportId);
        String level = severity(minSeverity);
        try {
            String markdown = (level == null
                    ? aiServiceClient.get().uri("/drift/reports/{id}/markdown", reportId)
                    : aiServiceClient.get().uri("/drift/reports/{id}/markdown?min_severity={s}", reportId, level))
                    .retrieve().body(String.class);
            if (markdown == null || markdown.isBlank()) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an empty report.");
            }
            return markdown;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw ApiException.notFound("Drift report not found in the AI service.");
            }
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return the drift report.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not return the drift report.");
        }
    }

    /** LD-157 / LD-158: severity levels and rules, for the legend of the drift screen. */
    public JsonNode severityRules() {
        JsonNode rules = getAiJson(aiServiceClient.get().uri("/drift/severity-rules"),
                "The AI service could not return the severity rules.");
        if (!rules.isObject() || !rules.path("levels").isArray()) {
            throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid response.");
        }
        return rules;
    }

    /** Owner check; returns the repository name when a repository id is given. */
    private String requireReport(String userId, UUID repositoryId, String reportId) {
        String repository = repositoryId == null ? null
                : repositorySyncService.requireOwned(userId, repositoryId).getFullName();
        String owner = reportOwners.get(reportId);
        if (owner == null) {
            throw ApiException.notFound("Drift report not found or the service was restarted.");
        }
        if (!Objects.equals(owner, userId)) {
            throw ApiException.forbidden("This drift report belongs to another user.");
        }
        return repository;
    }

    private static String severity(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String level = value.trim().toLowerCase(Locale.ROOT);
        if (!SEVERITY_LEVELS.contains(level)) {
            throw ApiException.badRequest("minSeverity must be one of low, medium, high, critical.");
        }
        return level;
    }

    // ------------------------------------------------------------------ GitHub

    private static int requireNumber(DriftAnalysisRequest request) {
        if (request == null || request.pullRequestNumber() == null || request.pullRequestNumber() < 1) {
            throw ApiException.badRequest("pullRequestNumber is required and must be a positive number.");
        }
        return request.pullRequestNumber();
    }

    /** Diff của PR tính từ merge base; không lấy được thì dùng đầu nhánh base (kèm cảnh báo). */
    private String mergeBase(Context ctx, GitHubPullRequest pr) {
        try {
            String sha = gitHubClient.getMergeBase(ctx.token(), ctx.owner, ctx.name, pr.base().sha(), pr.head().sha());
            if (sha != null && !sha.isBlank()) {
                return sha;
            }
        } catch (GitHubApiException e) {
            rethrowIfUnauthorized(e, ctx);
        }
        ctx.warnings.add("Merge base of the pull request is unknown; the code before the change was read from "
                + "the head of " + pr.base().ref() + ".");
        return pr.base().sha();
    }

    /** Tải nội dung file Python/Java ở 2 phía và phân tích bằng code-analyzer. */
    private void analyzeSources(Context ctx, List<GitHubPullRequestFile> files, String baseSha, String headSha,
                                Map<String, JsonNode> before, Map<String, JsonNode> after) {
        List<GitHubPullRequestFile> analyzable = files.stream()
                .filter(f -> isAnalyzed(f.filename()))
                .filter(f -> !"unchanged".equals(f.status()))
                .toList();
        if (analyzable.isEmpty()) {
            return;
        }
        if (analyzable.size() > MAX_ANALYZED_FILES) {
            ctx.warnings.add((analyzable.size() - MAX_ANALYZED_FILES) + " source file(s) beyond the first "
                    + MAX_ANALYZED_FILES + " were checked from the diff only.");
            analyzable = analyzable.subList(0, MAX_ANALYZED_FILES);
        }

        Map<String, GitHubTree.Entry> baseTree = null;
        List<AnalysisInput.FileInput> baseInputs = new ArrayList<>();
        List<AnalysisInput.FileInput> headInputs = new ArrayList<>();
        for (GitHubPullRequestFile f : analyzable) {
            String language = LanguageDetector.detect(f.filename());
            if (!"removed".equals(f.status())) {
                String text = blobText(ctx, f.sha(), f.filename(), null);
                if (text != null) {
                    headInputs.add(new AnalysisInput.FileInput(f.filename(), language, text));
                }
            }
            if (!"added".equals(f.status())) {
                if (baseTree == null) {
                    baseTree = tree(ctx, baseSha);
                }
                String oldPath = f.previousFilename() != null ? f.previousFilename() : f.filename();
                GitHubTree.Entry entry = baseTree.get(oldPath);
                String text = entry == null ? null : blobText(ctx, entry.sha(), oldPath, entry.size());
                if (entry == null) {
                    ctx.warnings.add(oldPath + ": not found at the base commit; checked from the diff only.");
                }
                if (text != null) {
                    baseInputs.add(new AnalysisInput.FileInput(oldPath, language, text));
                }
            }
        }
        // analysis of a file is stored under its head path (the AI service pairs before/after by file)
        Map<String, String> headPathOf = new HashMap<>();
        for (GitHubPullRequestFile f : analyzable) {
            headPathOf.put(f.previousFilename() != null ? f.previousFilename() : f.filename(), f.filename());
        }
        analyze(ctx, baseInputs, "base").forEach((path, a) -> before.put(headPathOf.getOrDefault(path, path), a));
        after.putAll(analyze(ctx, headInputs, "head"));
    }

    /** Cây thư mục của một commit: path -> blob. Lỗi (trừ token hỏng) trả về cây rỗng kèm cảnh báo. */
    private Map<String, GitHubTree.Entry> tree(Context ctx, String commitSha) {
        Map<String, GitHubTree.Entry> out = new LinkedHashMap<>();
        try {
            GitHubCommit commit = gitHubClient.getCommit(ctx.token(), ctx.owner, ctx.name, commitSha);
            if (commit == null || commit.commit() == null || commit.commit().tree() == null) {
                ctx.warnings.add("GitHub returned no file tree for commit " + shortSha(commitSha) + ".");
                return out;
            }
            GitHubTree tree = gitHubClient.getTree(ctx.token(), ctx.owner, ctx.name, commit.commit().tree().sha());
            if (tree == null || tree.tree() == null) {
                return out;
            }
            if (tree.truncated()) {
                ctx.warnings.add("The file tree of commit " + shortSha(commitSha)
                        + " is too large; GitHub returned only part of it.");
            }
            for (GitHubTree.Entry e : tree.tree()) {
                if ("blob".equals(e.type()) && e.path() != null) {
                    out.put(e.path(), e);
                }
            }
        } catch (GitHubApiException e) {
            rethrowIfUnauthorized(e, ctx);
            ctx.warnings.add("Could not read the file tree of commit " + shortSha(commitSha) + " from GitHub.");
        }
        return out;
    }

    /** Nội dung UTF-8 của một blob; null (kèm cảnh báo) nếu quá lớn, nhị phân hoặc GitHub lỗi. */
    private String blobText(Context ctx, String sha, String path, Long knownSize) {
        if (sha == null || sha.isBlank()) {
            return null;
        }
        if (knownSize != null && knownSize > MAX_SOURCE_BYTES) {
            ctx.warnings.add(path + ": larger than " + MAX_SOURCE_BYTES + " bytes; checked from the diff only.");
            return null;
        }
        try {
            GitHubBlob blob = gitHubClient.getBlob(ctx.token(), ctx.owner, ctx.name, sha);
            byte[] bytes = decode(blob);
            if (bytes == null || bytes.length > MAX_SOURCE_BYTES || looksBinary(bytes)) {
                ctx.warnings.add(path + ": content could not be read from GitHub; checked from the diff only.");
                return null;
            }
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (GitHubApiException e) {
            rethrowIfUnauthorized(e, ctx);
            ctx.warnings.add(path + ": content could not be read from GitHub; checked from the diff only.");
            return null;
        }
    }

    /** README và các file Markdown của repo ở commit head (ưu tiên README, rồi thư mục docs/). */
    private List<ObjectNode> repositoryDocs(Context ctx, String headSha) {
        List<GitHubTree.Entry> markdown = tree(ctx, headSha).values().stream()
                .filter(e -> e.path().toLowerCase(Locale.ROOT).endsWith(".md"))
                .filter(e -> Arrays.stream(e.path().split("/")).noneMatch(SKIPPED_DIRECTORIES::contains))
                .sorted(Comparator.comparingInt((GitHubTree.Entry e) -> docRank(e.path()))
                        .thenComparing(GitHubTree.Entry::path))
                .toList();
        if (markdown.size() > MAX_REPOSITORY_DOCS) {
            ctx.warnings.add("Only " + MAX_REPOSITORY_DOCS + " of " + markdown.size()
                    + " Markdown files of the repository were checked.");
            markdown = markdown.subList(0, MAX_REPOSITORY_DOCS);
        }
        List<ObjectNode> out = new ArrayList<>();
        for (GitHubTree.Entry e : markdown) {
            String text = blobText(ctx, e.sha(), e.path(), e.size());
            if (text == null || text.isBlank()) {
                continue;
            }
            if (text.length() > MAX_DOC_CHARS) {
                ctx.warnings.add(e.path() + ": only the first " + MAX_DOC_CHARS + " characters were checked.");
                text = text.substring(0, MAX_DOC_CHARS);
            }
            ObjectNode doc = json.objectNode();
            doc.put("path", e.path());
            doc.put("content", text);
            out.add(doc);
        }
        return out;
    }

    /** Python / Java: ngôn ngữ code-analyzer phân tích được. Set.of(...).contains(null) ném lỗi nên kiểm tra null trước. */
    private static boolean isAnalyzed(String path) {
        String language = path == null ? null : LanguageDetector.detect(path);
        return language != null && ANALYZED_LANGUAGES.contains(language);
    }

    private static int docRank(String path) {
        String lower = path.toLowerCase(Locale.ROOT);
        if (lower.equals("readme.md")) return 0;
        if (lower.endsWith("/readme.md") || lower.startsWith("readme")) return 1;
        if (lower.startsWith("docs/") || lower.startsWith("doc/")) return 2;
        return 3;
    }

    private GitHubApiException rethrowIfUnauthorized(GitHubApiException e, Context ctx) {
        if (e.isUnauthorized()) {
            connectionService.markInvalid(ctx.connection);
            throw ApiException.githubReauthRequired();
        }
        if (e.isRateLimited()) {
            throw e;   // every later call would fail too: GlobalExceptionHandler answers 502 + message
        }
        return e;
    }

    private RuntimeException translate(GitHubApiException e, Context ctx, String notFoundMessage, String code) {
        rethrowIfUnauthorized(e, ctx);
        if (e.isNotFound()) {
            return new ApiException(HttpStatus.NOT_FOUND, code, notFoundMessage);
        }
        return e;
    }

    // ------------------------------------------------------------------ code analyzer

    /** path -> FileAnalysis của code-analyzer; lỗi -> rỗng kèm cảnh báo (ai-service dùng diff). */
    private Map<String, JsonNode> analyze(Context ctx, List<AnalysisInput.FileInput> inputs, String side) {
        Map<String, JsonNode> out = new HashMap<>();
        if (inputs.isEmpty()) {
            return out;
        }
        try {
            ResponseEntity<JsonNode> response = analyzerClient.post()
                    .uri("/api/v1/analyze-repo")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new AnalysisInput("repository", ctx.fullName, inputs))
                    .retrieve()
                    .toEntity(JsonNode.class);
            JsonNode files = response.getBody() == null ? null : response.getBody().path("files");
            if (files == null || !files.isArray()) {
                ctx.warnings.add("The code analyzer returned an invalid response for the " + side
                        + " commit; changes were read from the diff only.");
                return out;
            }
            for (JsonNode f : files) {
                if (f.path("path").isTextual()) {
                    out.put(f.path("path").asText(), f);
                }
            }
        } catch (RestClientException e) {
            ctx.warnings.add("The code analyzer could not analyze the " + side
                    + " commit; changes were read from the diff only.");
        }
        return out;
    }

    // ------------------------------------------------------------------ AI service

    /** Tài liệu đã lưu cần kiểm tra: chỉ tài liệu sinh cho repo này (target = owner/name). */
    private List<String> documentIds(Context ctx, List<String> requested) {
        JsonNode documents = getAiJson(aiServiceClient.get().uri("/documents"),
                "The AI service could not list saved documents.");
        Set<String> ofRepository = new LinkedHashSet<>();
        if (documents.isArray()) {
            for (JsonNode d : documents) {
                if (ctx.fullName.equalsIgnoreCase(d.path("target").asText())) {
                    ofRepository.add(d.path("id").asText());
                }
            }
        }
        if (requested == null) {
            return new ArrayList<>(ofRepository);
        }
        List<String> out = new ArrayList<>();
        for (String id : new LinkedHashSet<>(requested)) {
            if (ofRepository.contains(id)) {
                out.add(id);
            } else {
                ctx.warnings.add("Document '" + id + "' is not a document of " + ctx.fullName
                        + "; it was not checked.");
            }
        }
        return out;
    }

    private ObjectNode driftRequest(Context ctx, GitHubPullRequest pr, int number, String baseSha,
                                    List<GitHubPullRequestFile> files, Map<String, JsonNode> before,
                                    Map<String, JsonNode> after, List<ObjectNode> docs, List<String> documentIds) {
        ObjectNode body = json.objectNode();
        body.put("repository", ctx.fullName);
        ObjectNode p = body.putObject("pull_request");
        p.put("number", number);
        p.put("title", cut(pr.title(), 500) == null ? "" : cut(pr.title(), 500));
        putIfPresent(p, "body", cut(pr.body(), 20_000));
        putIfPresent(p, "url", cut(pr.htmlUrl(), 500));
        putIfPresent(p, "author", pr.user() == null ? null : cut(pr.user().login(), 200));
        putIfPresent(p, "head_branch", cut(pr.head().ref(), 300));
        putIfPresent(p, "base_branch", cut(pr.base().ref(), 300));
        p.put("head_sha", pr.head().sha());
        p.put("base_sha", baseSha);

        ArrayNode out = body.putArray("files");
        Set<String> seen = new LinkedHashSet<>();
        for (GitHubPullRequestFile f : files) {
            if (f.filename() == null || !seen.add(f.filename())) {
                continue;     // the AI service rejects duplicate paths
            }
            ObjectNode n = out.addObject();
            n.put("path", f.filename());
            n.put("status", f.status() != null && GITHUB_STATUSES.contains(f.status()) ? f.status() : "modified");
            putIfPresent(n, "previous_path", f.previousFilename());
            if (f.patch() != null && f.patch().length() <= MAX_PATCH_CHARS) {
                n.put("patch", f.patch());
            } else if (f.patch() != null) {
                ctx.warnings.add(f.filename() + ": the diff is too large and was not checked line by line.");
            }
            if (before.containsKey(f.filename())) {
                n.set("before", before.get(f.filename()));
            }
            if (after.containsKey(f.filename())) {
                n.set("after", after.get(f.filename()));
            }
        }
        ArrayNode docsNode = body.putArray("docs");
        docs.forEach(docsNode::add);
        ArrayNode ids = body.putArray("document_ids");
        documentIds.forEach(ids::add);
        return body;
    }

    private ObjectNode postDrift(ObjectNode body) {
        JsonNode report;
        try {
            ResponseEntity<JsonNode> response = aiServiceClient.post()
                    .uri("/drift/analyze")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .toEntity(JsonNode.class);
            if (response.getStatusCode().value() != 201) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE",
                        "The AI service returned an unexpected HTTP status.");
            }
            report = response.getBody();
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 422) {
                String detail = DocumentationTemplateService.detail(e);
                throw new ApiException(HttpStatus.BAD_REQUEST, "DRIFT_REQUEST_INVALID",
                        detail != null ? detail : "The pull request could not be checked for documentation drift.");
            }
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not analyze documentation drift.");
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", "The AI service could not analyze documentation drift.");
        }
        if (report == null || !report.isObject() || !report.path("id").isTextual()
                || !report.path("status").isTextual()) {
            throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an invalid drift report.");
        }
        return (ObjectNode) report;
    }

    private JsonNode getAiJson(RestClient.RequestHeadersSpec<?> request, String message) {
        try {
            JsonNode result = request.retrieve().body(JsonNode.class);
            if (result == null) {
                throw integrationFailure("AI_SERVICE_INVALID_RESPONSE", "The AI service returned an empty response.");
            }
            return result;
        } catch (RestClientResponseException e) {
            if (e.getStatusCode().value() == 404) {
                throw ApiException.notFound("Drift report not found in the AI service.");
            }
            throw integrationFailure("AI_SERVICE_FAILED", message);
        } catch (RestClientException e) {
            throw integrationFailure("AI_SERVICE_FAILED", message);
        }
    }

    // ------------------------------------------------------------------ helpers

    private static void putIfPresent(ObjectNode node, String field, String value) {
        if (value != null && !value.isBlank()) {
            node.put(field, value);
        }
    }

    private static String cut(String value, int max) {
        return value == null || value.length() <= max ? value : value.substring(0, max);
    }

    private static String shortSha(String sha) {
        return sha == null ? "?" : sha.substring(0, Math.min(7, sha.length()));
    }

    static byte[] decode(GitHubBlob blob) {
        if (blob == null || blob.content() == null) {
            return null;
        }
        if (blob.encoding() == null || "base64".equalsIgnoreCase(blob.encoding())) {
            try {
                return Base64.getMimeDecoder().decode(blob.content());
            } catch (IllegalArgumentException e) {
                return null;
            }
        }
        return blob.content().getBytes(StandardCharsets.UTF_8);
    }

    private static boolean looksBinary(byte[] bytes) {
        int n = Math.min(bytes.length, 8000);
        for (int i = 0; i < n; i++) {
            if (bytes[i] == 0) {
                return true;
            }
        }
        return false;
    }

    private ApiException integrationFailure(String code, String message) {
        return new ApiException(HttpStatus.BAD_GATEWAY, code, message);
    }

    /** Repo, token và cảnh báo của một lần phân tích. */
    private static final class Context {
        final String fullName;
        final String owner;
        final String name;
        final GitHubConnection connection;
        final List<String> warnings = new ArrayList<>();

        Context(String fullName, GitHubConnection connection) {
            this.fullName = fullName;
            String[] parts = fullName.split("/", 2);
            if (parts.length != 2 || parts[0].isBlank() || parts[1].isBlank()) {
                throw ApiException.badRequest("Repository name '" + fullName + "' is not in the form owner/name.");
            }
            this.owner = parts[0];
            this.name = parts[1];
            this.connection = connection;
        }

        String token() {
            return connection.getAccessToken();
        }
    }
}
