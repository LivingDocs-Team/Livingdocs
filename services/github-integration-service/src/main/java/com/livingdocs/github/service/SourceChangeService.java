package com.livingdocs.github.service;

import com.livingdocs.github.change.ChangedEntity;
import com.livingdocs.github.change.ChangedEntityDetector;
import com.livingdocs.github.change.CodeAnalyzerClient;
import com.livingdocs.github.change.CodeEntity;
import com.livingdocs.github.change.SourceChangeException;
import com.livingdocs.github.change.SourceChangeRequest;
import com.livingdocs.github.change.UnifiedDiff;
import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubChangedFile;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.dto.SourceChangeResponse;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.entity.SourceChangeEntity;
import com.livingdocs.github.entity.SourceChangeFile;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.repository.SourceChangeRepository;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.LanguageDetector;
import com.livingdocs.github.sync.PathFilter;
import com.livingdocs.github.sync.SyncOptions;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * LD-116 - phát hiện thay đổi mã nguồn của một commit hoặc Pull Request:
 * lấy file thay đổi từ GitHub (LD-117..119), tìm code entity thay đổi bằng Code Analyzer (LD-120)
 * và lưu thành source change PENDING để bước cập nhật tài liệu (LD-128) đọc qua API.
 * Lỗi GitHub / analyzer được lưu thành FAILED kèm mã lỗi; người dùng gọi retry để chạy lại.
 */
@Service
public class SourceChangeService {

    static final int MAX_FILES = 50;
    static final int LIST_LIMIT = 50;

    private final ConnectedRepositoryRepository repositoryRepository;
    private final GitHubConnectionRepository connectionRepository;
    private final GitHubConnectionService connectionService;
    private final GitHubClient gitHubClient;
    private final CodeAnalyzerClient analyzerClient;
    private final SourceChangeRepository sourceChangeRepository;
    private final TransactionTemplate transaction;

    public SourceChangeService(ConnectedRepositoryRepository repositoryRepository,
                               GitHubConnectionRepository connectionRepository,
                               GitHubConnectionService connectionService,
                               GitHubClient gitHubClient,
                               CodeAnalyzerClient analyzerClient,
                               SourceChangeRepository sourceChangeRepository,
                               PlatformTransactionManager transactionManager) {
        this.repositoryRepository = repositoryRepository;
        this.connectionRepository = connectionRepository;
        this.connectionService = connectionService;
        this.gitHubClient = gitHubClient;
        this.analyzerClient = analyzerClient;
        this.sourceChangeRepository = sourceChangeRepository;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /**
     * Phát hiện và lưu kết quả. Gọi GitHub và analyzer ngoài transaction (có thể mất vài giây),
     * rồi lưu trong một transaction ngắn. Không có file mã nguồn nào thay đổi thì không lưu gì.
     */
    public void detect(SourceChangeRequest request) {
        ConnectedRepository repo = repositoryRepository.findById(request.repositoryId()).orElse(null);
        if (repo == null) {
            return; // repo vừa bị gỡ khỏi workspace
        }
        Result result;
        try {
            result = Result.found(findChangedFiles(repo, request));
        } catch (GitHubApiException e) {
            result = Result.failed(errorCode(e), e.getMessage());
        } catch (SourceChangeException e) {
            result = Result.failed(e.getCode(), e.getMessage());
        } catch (ApiException e) { // GitHub chưa kết nối hoặc cần kết nối lại
            result = Result.failed(e.getCode(), e.getMessage());
        }
        save(request, result);
    }

    @Transactional(readOnly = true)
    public List<SourceChangeResponse> list(UUID repositoryId) {
        return sourceChangeRepository.findByRepositoryIdOrderByCreatedAtDesc(repositoryId, PageRequest.of(0, LIST_LIMIT))
                .stream().map(SourceChangeResponse::from).toList();
    }

    /** Chạy lại một source change FAILED. Kết quả rỗng nghĩa là lần này không còn file mã nguồn nào thay đổi. */
    public Optional<SourceChangeResponse> retry(UUID repositoryId, UUID changeId) {
        SourceChange change = sourceChangeRepository.findById(changeId)
                .filter(c -> c.getRepositoryId().equals(repositoryId))
                .orElseThrow(() -> ApiException.notFound("Source change " + changeId + " was not found."));
        if (change.getStatus() != SourceChange.Status.FAILED) {
            throw new ApiException(HttpStatus.CONFLICT, "SOURCE_CHANGE_NOT_FAILED",
                    "Only a failed source change can be retried.");
        }
        detect(new SourceChangeRequest(repositoryId, change.getTriggerType(), change.getCommitSha(),
                change.getPullRequestNumber()));
        return transaction.execute(status -> sourceChangeRepository.findById(changeId).map(SourceChangeResponse::from));
    }

    // ------------------------------------------------------------------ phát hiện

    private List<SourceChangeFile> findChangedFiles(ConnectedRepository repo, SourceChangeRequest request) {
        String token = accessToken(repo);
        String[] ownerAndName = repo.getFullName().split("/", 2);
        String owner = ownerAndName[0];
        String name = ownerAndName[1];
        List<GitHubChangedFile> changed = request.trigger() == SourceChange.Trigger.COMMIT
                ? gitHubClient.getCommitFiles(token, owner, name, request.commitSha())
                : gitHubClient.listPullRequestChangedFiles(token, owner, name, request.pullRequestNumber());
        List<GitHubChangedFile> sources = changed.stream().filter(SourceChangeService::isSourceFile).toList();

        List<SourceChangeFile> rows = new ArrayList<>();
        Map<String, UnifiedDiff> diffs = new HashMap<>();
        List<AnalysisInput.FileInput> afterFiles = new ArrayList<>();
        List<AnalysisInput.FileInput> beforeFiles = new ArrayList<>();
        for (GitHubChangedFile file : sources) {
            SourceChangeFile row = toRow(file);
            rows.add(row);
            if (rows.size() > MAX_FILES) {
                row.setSkippedReason("TOO_MANY_FILES");
                continue;
            }
            if (file.patch() == null) {
                row.setSkippedReason("PATCH_UNAVAILABLE"); // file quá lớn, GitHub không gửi diff
                continue;
            }
            String after = "";
            if (!"REMOVED".equals(row.getChangeType())) {
                GitHubBlob blob = gitHubClient.getBlob(token, owner, name, file.sha());
                if (blob != null && blob.size() != null && blob.size() > SyncOptions.DEFAULT_MAX_FILE_SIZE_BYTES) {
                    row.setSkippedReason("FILE_TOO_LARGE");
                    continue;
                }
                after = decode(blob);
                if (after == null) {
                    row.setSkippedReason("NOT_ANALYZED");
                    continue;
                }
            }
            UnifiedDiff diff = UnifiedDiff.parse(file.patch());
            // Nội dung trước thay đổi dựng lại từ nội dung sau + patch, không cần gọi thêm GitHub
            String before = "ADDED".equals(row.getChangeType()) ? "" : diff.reconstructOld(after);
            diffs.put(row.getPath(), diff);
            if (!after.isEmpty()) {
                afterFiles.add(new AnalysisInput.FileInput(row.getPath(), row.getLanguage(), after));
            }
            if (!before.isEmpty()) {
                beforeFiles.add(new AnalysisInput.FileInput(row.getPath(), row.getLanguage(), before));
            }
        }

        Map<String, List<CodeEntity>> afterEntities = analyze(repo.getFullName(), afterFiles);
        Map<String, List<CodeEntity>> beforeEntities = analyze(repo.getFullName(), beforeFiles);
        for (SourceChangeFile row : rows) {
            UnifiedDiff diff = diffs.get(row.getPath());
            if (diff == null) {
                continue; // đã ghi lý do bỏ qua ở trên
            }
            List<CodeEntity> after = entitiesOf(afterFiles, afterEntities, row.getPath());
            List<CodeEntity> before = entitiesOf(beforeFiles, beforeEntities, row.getPath());
            if (after == null || before == null) {
                row.setSkippedReason("NOT_ANALYZED"); // analyzer báo file rỗng / lỗi cú pháp / không hỗ trợ
                continue;
            }
            for (ChangedEntity entity : ChangedEntityDetector.detect(before, after, diff)) {
                row.getEntities().add(new SourceChangeEntity(entity));
            }
        }
        return rows;
    }

    /** Không gọi Code Analyzer khi không có file nào để phân tích (vd. commit chỉ sửa README, hoặc chỉ thêm file mới). */
    private Map<String, List<CodeEntity>> analyze(String target, List<AnalysisInput.FileInput> files) {
        return files.isEmpty() ? Map.of() : analyzerClient.analyze(target, files);
    }

    private String accessToken(ConnectedRepository repo) {
        GitHubConnection connection = connectionRepository.findById(repo.getConnectionId())
                .orElseThrow(ApiException::githubNotConnected);
        return connectionService.getActiveConnection(connection.getUserId()).getAccessToken(); // tự làm mới token
    }

    /** Cùng quy tắc chọn file như khi đồng bộ (LD-63): Java/Python, bỏ thư viện và file build. */
    static boolean isSourceFile(GitHubChangedFile file) {
        String language = LanguageDetector.detect(file.filename());
        return language != null && SyncOptions.ANALYZER_LANGUAGES.contains(language)
                && !PathFilter.isIgnored(file.filename());
    }

    private static SourceChangeFile toRow(GitHubChangedFile file) {
        SourceChangeFile row = new SourceChangeFile();
        row.setPath(file.filename());
        row.setPreviousPath(file.previousFilename());
        row.setChangeType(switch (file.status() == null ? "" : file.status()) {
            case "added" -> "ADDED";
            case "removed" -> "REMOVED";
            case "renamed" -> "RENAMED";
            default -> "MODIFIED";
        });
        row.setLanguage(LanguageDetector.detect(file.filename()));
        row.setAdditions(file.additions());
        row.setDeletions(file.deletions());
        return row;
    }

    /** Entity của file: rỗng nếu file không có nội dung ở phía đó, null nếu analyzer không phân tích được. */
    private static List<CodeEntity> entitiesOf(List<AnalysisInput.FileInput> sent,
                                               Map<String, List<CodeEntity>> analyzed, String path) {
        boolean wasSent = sent.stream().anyMatch(f -> f.path().equals(path));
        return wasSent ? analyzed.get(path) : List.of();
    }

    private static String decode(GitHubBlob blob) {
        if (blob == null || blob.content() == null) {
            return null;
        }
        try {
            byte[] bytes = blob.encoding() == null || "base64".equalsIgnoreCase(blob.encoding())
                    ? Base64.getMimeDecoder().decode(blob.content())
                    : blob.content().getBytes(StandardCharsets.UTF_8);
            return new String(bytes, StandardCharsets.UTF_8);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /** Mã lỗi giống bảng lỗi đồng bộ (docs/repository-sync-contract.md) để frontend dùng chung thông báo. */
    static String errorCode(GitHubApiException e) {
        if (e.isNetworkError()) {
            return "GITHUB_UNAVAILABLE";
        }
        if (e.isRateLimited()) {
            return "RATE_LIMITED";
        }
        int status = e.getStatusCode();
        if (status == 401) {
            return "TOKEN_INVALID";
        }
        if (status == 403) {
            return "ACCESS_DENIED";
        }
        if (status == 404 || status == 422) {
            return "REPOSITORY_NOT_FOUND";
        }
        return status >= 500 ? "GITHUB_UNAVAILABLE" : "UNEXPECTED_GITHUB_RESPONSE";
    }

    // ------------------------------------------------------------------ lưu

    private void save(SourceChangeRequest request, Result result) {
        transaction.executeWithoutResult(status -> {
            SourceChange change = sourceChangeRepository.findByRepositoryIdAndTriggerTypeAndCommitSha(
                    request.repositoryId(), request.trigger(), request.commitSha()).orElse(null);
            if (result.files() != null && result.files().isEmpty()) {
                if (change != null) {
                    sourceChangeRepository.delete(change); // chạy lại và không còn file mã nguồn nào thay đổi
                }
                return;
            }
            if (change == null) {
                change = new SourceChange();
                change.setRepositoryId(request.repositoryId());
                change.setTriggerType(request.trigger());
                change.setCommitSha(request.commitSha());
                change.setPullRequestNumber(request.pullRequestNumber());
            }
            if (result.files() == null) {
                change.markFailed(result.errorCode(), result.errorMessage());
            } else {
                change.markPending(result.files());
            }
            sourceChangeRepository.save(change);
        });
    }

    private record Result(List<SourceChangeFile> files, String errorCode, String errorMessage) {

        static Result found(List<SourceChangeFile> files) {
            return new Result(files, null, null);
        }

        static Result failed(String errorCode, String errorMessage) {
            return new Result(null, errorCode, errorMessage);
        }
    }
}
