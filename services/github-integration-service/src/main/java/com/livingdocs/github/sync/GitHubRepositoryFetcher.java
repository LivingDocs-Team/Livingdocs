package com.livingdocs.github.sync;

import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubRepoDetails;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.sync.RepositorySnapshot.CommitInfo;
import com.livingdocs.github.sync.RepositorySnapshot.RepositoryInfo;
import com.livingdocs.github.sync.RepositorySnapshot.SkipReason;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import com.livingdocs.github.sync.RepositorySnapshot.SyncStats;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import java.util.regex.Pattern;

/**
 * LD-63 (phần Đăng): lấy thông tin một repository từ GitHub để đồng bộ.
 *
 * Các bước, tất cả đều theo cùng một commit để dữ liệu nhất quán:
 * <ol>
 *   <li>Thông tin repo (GET /repos/{owner}/{repo})</li>
 *   <li>Commit mới nhất của nhánh (GET /repos/{owner}/{repo}/commits/{branch})</li>
 *   <li>Cây thư mục của commit đó, 1 lần gọi (GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1)</li>
 *   <li>Chọn file nguồn (java, python...) rồi tải nội dung theo SHA (GET .../git/blobs/{sha})</li>
 *   <li>Thống kê ngôn ngữ và các commit gần nhất (không bắt buộc, lỗi thì chỉ cảnh báo)</li>
 *   <li>Kiểm tra lại dữ liệu trước khi trả về (SnapshotVerifier)</li>
 * </ol>
 *
 * Lỗi GitHub được chuyển thành {@link RepositorySyncException} với {@link SyncErrorCode} rõ ràng.
 * Lớp này không ghi database: việc lưu kết quả và trả API do phần của Minh đảm nhận.
 */
@Service
public class GitHubRepositoryFetcher {

    private static final Logger log = LoggerFactory.getLogger(GitHubRepositoryFetcher.class);

    /** owner: chữ, số, dấu gạch ngang (tối đa 39 ký tự); repo: chữ, số, ".", "_", "-" (tối đa 100). */
    private static final Pattern FULL_NAME =
            Pattern.compile("^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$");
    private static final int BINARY_SNIFF_BYTES = 8000;
    private static final String SYMLINK_MODE = "120000";
    private static final int MAX_FILE_WARNINGS = 10;

    private final GitHubClient gitHubClient;

    public GitHubRepositoryFetcher(GitHubClient gitHubClient) {
        this.gitHubClient = gitHubClient;
    }

    enum Stage {
        REPOSITORY("đọc thông tin repository"),
        BRANCH("đọc commit mới nhất của nhánh"),
        TREE("đọc danh sách file"),
        CONTENT("tải nội dung file"),
        LANGUAGES("đọc thống kê ngôn ngữ"),
        COMMITS("đọc lịch sử commit");

        private final String description;

        Stage(String description) {
            this.description = description;
        }
    }

    /**
     * Lấy dữ liệu repository.
     *
     * @param accessToken token GitHub của người dùng (null = gọi ẩn danh, chỉ đọc được repo public)
     * @param fullName    dạng owner/repo, ví dụ LivingDocs-Team/Livingdocs
     * @param options     tuỳ chọn; null = {@link SyncOptions#defaults()}
     * @throws RepositorySyncException khi không đồng bộ được (xem {@link SyncErrorCode})
     */
    public RepositorySnapshot fetch(String accessToken, String fullName, SyncOptions options) {
        SyncOptions opts = options != null ? options : SyncOptions.defaults();
        String[] ownerAndRepo = parseFullName(fullName);
        String owner = ownerAndRepo[0];
        String repo = ownerAndRepo[1];
        String label = owner + "/" + repo;
        List<SyncWarning> warnings = new ArrayList<>();

        // 1. Thông tin repository
        GitHubRepoDetails details = required(Stage.REPOSITORY, label, null,
                () -> gitHubClient.getRepositoryDetails(accessToken, owner, repo));
        if (details == null || details.id() == null || isBlank(details.fullName())) {
            throw new RepositorySyncException(SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE,
                    "GitHub không trả về thông tin repository " + label
                            + " (repo có thể vừa đổi tên hoặc chuyển chủ sở hữu).");
        }
        if (details.disabled()) {
            throw new RepositorySyncException(SyncErrorCode.ACCESS_DENIED,
                    "Repository " + details.fullName() + " đã bị GitHub vô hiệu hoá nên không đọc được.");
        }
        if (details.archived()) {
            warnings.add(new SyncWarning("ARCHIVED_REPOSITORY",
                    "Repository đã được lưu trữ (archived): chỉ đọc, sẽ không có thay đổi mới."));
        }

        String branch = opts.branch() != null ? opts.branch() : details.defaultBranch();
        if (isBlank(branch)) {
            throw new RepositorySyncException(SyncErrorCode.EMPTY_REPOSITORY,
                    "Repository " + label + " chưa có nhánh nào nên không có gì để đồng bộ.");
        }

        // Repo có thể đã đổi tên: từ đây dùng tên thật GitHub trả về (SnapshotVerifier sẽ cảnh báo REPOSITORY_RENAMED)
        String[] actual = splitOrDefault(details.fullName(), ownerAndRepo);
        String o = actual[0];
        String r = actual[1];

        // 2. Commit mới nhất của nhánh
        GitHubCommit head = required(Stage.BRANCH, label, branch,
                () -> gitHubClient.getCommit(accessToken, o, r, branch));
        if (head == null || isBlank(head.sha()) || head.commit() == null
                || head.commit().tree() == null || isBlank(head.commit().tree().sha())) {
            throw new RepositorySyncException(SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE,
                    "GitHub không trả về commit mới nhất của nhánh '" + branch + "' trong " + label + ".");
        }

        // 3. Cây thư mục tại commit đó
        GitHubTree tree = required(Stage.TREE, label, branch,
                () -> gitHubClient.getTree(accessToken, o, r, head.commit().tree().sha()));
        if (tree == null || tree.tree() == null) {
            throw new RepositorySyncException(SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE,
                    "GitHub không trả về danh sách file của " + label + ".");
        }
        if (tree.truncated()) {
            warnings.add(new SyncWarning("TREE_TRUNCATED",
                    "Repository quá lớn, GitHub chỉ trả về một phần danh sách file."));
        }

        // 4. Chọn file nguồn và tải nội dung
        FileSelection selection = selectFiles(accessToken, o, r, label, tree, opts, warnings);

        // 5. Thông tin phụ: lỗi thì chỉ cảnh báo, không làm hỏng cả lần đồng bộ
        Map<String, Long> languages = optional(Stage.LANGUAGES, label, branch, warnings,
                "LANGUAGES_UNAVAILABLE", Map.of(),
                () -> gitHubClient.getLanguages(accessToken, o, r));

        List<CommitInfo> recentCommits = List.of();
        if (opts.recentCommitLimit() > 0) {
            List<GitHubCommit> commits = optional(Stage.COMMITS, label, branch, warnings,
                    "COMMITS_UNAVAILABLE", List.of(),
                    () -> gitHubClient.listCommits(accessToken, o, r, branch, opts.recentCommitLimit()));
            recentCommits = commits.stream()
                    .filter(c -> c != null && !isBlank(c.sha()))
                    .map(GitHubRepositoryFetcher::toCommitInfo)
                    .toList();
        }

        SyncStats stats = new SyncStats(
                selection.totalFiles(),
                selection.files().size(),
                selection.filesWithContent(),
                selection.filesIgnored(),
                tree.truncated(),
                selection.limitReached());

        RepositorySnapshot snapshot = new RepositorySnapshot(
                toRepositoryInfo(details),
                branch,
                toCommitInfo(head),
                languages,
                selection.files(),
                recentCommits,
                stats,
                warnings,
                Instant.now());

        // 6. Kiểm tra dữ liệu trước khi trả về
        RepositorySnapshot verified = SnapshotVerifier.verify(label, snapshot);
        log.info("Synced {}@{} ({}): {} source files, {} with content, {} warnings",
                verified.repository().fullName(), branch, shortSha(head.sha()),
                stats.filesSelected(), stats.filesWithContent(), verified.warnings().size());
        return verified;
    }

    // ------------------------------------------------------------------ chọn file

    private record FileSelection(List<SourceFile> files, int totalFiles, int filesWithContent,
                                 int filesIgnored, boolean limitReached) {
    }

    private FileSelection selectFiles(String accessToken, String owner, String repo, String label,
                                      GitHubTree tree, SyncOptions opts, List<SyncWarning> warnings) {
        List<GitHubTree.Entry> blobs = tree.tree().stream()
                .filter(e -> e != null && "blob".equals(e.type()) && e.path() != null)
                .filter(e -> !SYMLINK_MODE.equals(e.mode())) // symlink: nội dung chỉ là đường dẫn, không phải code
                .sorted(Comparator.comparing(GitHubTree.Entry::path))
                .toList();

        List<SourceFile> files = new ArrayList<>();
        List<SyncWarning> fileWarnings = new ArrayList<>();
        int ignored = 0;
        int unsafe = 0;
        int withContent = 0;
        boolean limitReached = false;

        for (GitHubTree.Entry entry : blobs) {
            String path = entry.path();
            if (!PathFilter.isSafe(path)) {
                unsafe++;
                ignored++;
                continue;
            }
            String language = LanguageDetector.detect(path);
            if (language == null || !opts.languages().contains(language) || PathFilter.isIgnored(path)) {
                ignored++;
                continue;
            }
            if (files.size() >= opts.maxFiles()) {
                limitReached = true;
                ignored++;
                continue;
            }
            long size = entry.size() == null ? 0L : entry.size();
            SourceFile file;
            if (!opts.includeContent()) {
                file = new SourceFile(path, entry.sha(), size, language, null, SkipReason.NOT_REQUESTED);
            } else if (size > opts.maxFileSizeBytes()) {
                file = new SourceFile(path, entry.sha(), size, language, null, SkipReason.TOO_LARGE);
            } else {
                file = downloadFile(accessToken, owner, repo, label, entry, size, language, fileWarnings);
            }
            if (file.hasContent()) {
                withContent++;
            }
            files.add(file);
        }

        if (unsafe > 0) {
            warnings.add(new SyncWarning("UNSAFE_PATHS_SKIPPED",
                    unsafe + " file có đường dẫn bất thường đã bị bỏ qua."));
        }
        if (limitReached) {
            warnings.add(new SyncWarning("FILE_LIMIT_REACHED",
                    "Chỉ lấy " + opts.maxFiles() + " file nguồn đầu tiên (theo thứ tự đường dẫn); tăng maxFiles nếu cần."));
        }
        if (files.isEmpty()) {
            warnings.add(new SyncWarning("NO_SOURCE_FILES",
                    "Không tìm thấy file " + String.join(", ", opts.languages().stream().sorted().toList())
                            + " nào để phân tích."));
        }
        warnings.addAll(fileWarnings.stream().limit(MAX_FILE_WARNINGS).toList());
        if (fileWarnings.size() > MAX_FILE_WARNINGS) {
            warnings.add(new SyncWarning("MORE_FILES_UNAVAILABLE",
                    "Còn " + (fileWarnings.size() - MAX_FILE_WARNINGS) + " file khác không tải được."));
        }
        return new FileSelection(files, blobs.size(), withContent, ignored, limitReached);
    }

    private SourceFile downloadFile(String accessToken, String owner, String repo, String label,
                                    GitHubTree.Entry entry, long size, String language,
                                    List<SyncWarning> fileWarnings) {
        GitHubBlob blob;
        try {
            blob = gitHubClient.getBlob(accessToken, owner, repo, entry.sha());
        } catch (GitHubApiException e) {
            RepositorySyncException error = translate(e, Stage.CONTENT, label, null);
            if (stopsDownloads(error.getCode())) {
                throw error; // token hỏng / hết lượt gọi API / mất mạng: tải tiếp các file khác cũng vô ích
            }
            fileWarnings.add(new SyncWarning("FILE_UNAVAILABLE", entry.path() + ": " + error.getMessage()));
            return new SourceFile(entry.path(), entry.sha(), size, language, null, SkipReason.UNAVAILABLE);
        }

        byte[] bytes = decode(blob);
        if (bytes == null) {
            fileWarnings.add(new SyncWarning("FILE_UNAVAILABLE",
                    entry.path() + ": GitHub trả về nội dung không đọc được."));
            return new SourceFile(entry.path(), entry.sha(), size, language, null, SkipReason.UNAVAILABLE);
        }
        if (looksBinary(bytes)) {
            return new SourceFile(entry.path(), entry.sha(), size, language, null, SkipReason.BINARY);
        }
        return new SourceFile(entry.path(), entry.sha(), size, language, toText(bytes), null);
    }

    // ------------------------------------------------------------------ xử lý lỗi

    private <T> T required(Stage stage, String label, String branch, Supplier<T> call) {
        try {
            return call.get();
        } catch (GitHubApiException e) {
            throw translate(e, stage, label, branch);
        }
    }

    private <T> T optional(Stage stage, String label, String branch, List<SyncWarning> warnings,
                           String warningCode, T fallback, Supplier<T> call) {
        try {
            T result = call.get();
            return result != null ? result : fallback;
        } catch (GitHubApiException e) {
            RepositorySyncException error = translate(e, stage, label, branch);
            if (error.getCode() == SyncErrorCode.TOKEN_INVALID || error.getCode() == SyncErrorCode.RATE_LIMITED) {
                throw error; // các bước sau chắc chắn cũng lỗi theo
            }
            warnings.add(new SyncWarning(warningCode, error.getMessage()));
            return fallback;
        }
    }

    /** Khi tải nội dung file gặp các lỗi này thì dừng, vì tải tiếp các file khác cũng sẽ lỗi. */
    private static boolean stopsDownloads(SyncErrorCode code) {
        return code == SyncErrorCode.TOKEN_INVALID
                || code == SyncErrorCode.RATE_LIMITED
                || code == SyncErrorCode.GITHUB_UNAVAILABLE
                || code == SyncErrorCode.ACCESS_DENIED;
    }

    /** Chuyển lỗi HTTP của GitHub thành lỗi đồng bộ dễ hiểu. */
    RepositorySyncException translate(GitHubApiException e, Stage stage, String label, String branch) {
        if (e.isNetworkError()) {
            return new RepositorySyncException(SyncErrorCode.GITHUB_UNAVAILABLE,
                    "Không kết nối được tới GitHub (mất mạng hoặc quá thời gian chờ). Thử lại sau.", null, e);
        }
        if (e.isRateLimited()) {
            Instant retryAt = e.retryAt();
            return new RepositorySyncException(SyncErrorCode.RATE_LIMITED,
                    "Đã vượt giới hạn số lần gọi GitHub API"
                            + (retryAt != null ? ", thử lại sau " + retryAt : ", thử lại sau ít phút") + ".",
                    retryAt, e);
        }
        int status = e.getStatusCode();
        if (status == 401) {
            return new RepositorySyncException(SyncErrorCode.TOKEN_INVALID,
                    "Token GitHub không hợp lệ hoặc đã hết hạn. Người dùng cần kết nối lại GitHub.", null, e);
        }
        if (status == 403) {
            return new RepositorySyncException(SyncErrorCode.ACCESS_DENIED,
                    "GitHub App không có quyền đọc repository " + label
                            + ". Hãy cài app cho repo này và cấp quyền Contents (read).", null, e);
        }
        if ((status == 404 || status == 422) && stage == Stage.BRANCH) {
            return new RepositorySyncException(SyncErrorCode.BRANCH_NOT_FOUND,
                    "Không tìm thấy nhánh '" + branch + "' trong repository " + label + ".", null, e);
        }
        if (status == 404) {
            return new RepositorySyncException(SyncErrorCode.REPOSITORY_NOT_FOUND,
                    "Không tìm thấy repository " + label
                            + " (repo đã bị xoá, đổi tên, hoặc GitHub App chưa được cài cho repo này).", null, e);
        }
        if (status == 409) {
            return new RepositorySyncException(SyncErrorCode.EMPTY_REPOSITORY,
                    "Repository " + label + " chưa có commit nào nên không có gì để đồng bộ.", null, e);
        }
        if (status >= 500) {
            return new RepositorySyncException(SyncErrorCode.GITHUB_UNAVAILABLE,
                    "GitHub đang gặp sự cố (HTTP " + status + ") khi " + stage.description + ". Thử lại sau.", null, e);
        }
        return new RepositorySyncException(SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE,
                "GitHub trả về lỗi không mong đợi (HTTP " + status + ") khi " + stage.description + ".", null, e);
    }

    // ------------------------------------------------------------------ tiện ích

    /** Kiểm tra và tách "owner/repo". Sai định dạng thì báo INVALID_REPOSITORY, không gọi GitHub. */
    static String[] parseFullName(String fullName) {
        String trimmed = fullName == null ? "" : fullName.trim();
        if (!FULL_NAME.matcher(trimmed).matches()) {
            throw new RepositorySyncException(SyncErrorCode.INVALID_REPOSITORY,
                    "Tên repository không hợp lệ: '" + fullName
                            + "'. Định dạng đúng là owner/repo, ví dụ LivingDocs-Team/Livingdocs.");
        }
        int slash = trimmed.indexOf('/');
        String repo = trimmed.substring(slash + 1);
        if (repo.equals(".") || repo.equals("..")) {
            throw new RepositorySyncException(SyncErrorCode.INVALID_REPOSITORY,
                    "Tên repository không hợp lệ: '" + fullName + "'.");
        }
        return new String[]{trimmed.substring(0, slash), repo};
    }

    /** Tách "owner/repo" GitHub trả về; nếu bất thường thì giữ tên đã yêu cầu. */
    private static String[] splitOrDefault(String fullName, String[] fallback) {
        int slash = fullName == null ? -1 : fullName.indexOf('/');
        if (slash <= 0 || slash == fullName.length() - 1) {
            return fallback;
        }
        return new String[]{fullName.substring(0, slash), fullName.substring(slash + 1)};
    }

    static byte[] decode(GitHubBlob blob) {
        if (blob == null || blob.content() == null) {
            return null;
        }
        if (blob.encoding() == null || "base64".equalsIgnoreCase(blob.encoding())) {
            try {
                return Base64.getMimeDecoder().decode(blob.content()); // nội dung GitHub có xuống dòng
            } catch (IllegalArgumentException e) {
                return null;
            }
        }
        return blob.content().getBytes(StandardCharsets.UTF_8);
    }

    /** File văn bản không chứa byte 0; file nhị phân (ảnh, jar...) gần như luôn có. */
    static boolean looksBinary(byte[] bytes) {
        int limit = Math.min(bytes.length, BINARY_SNIFF_BYTES);
        for (int i = 0; i < limit; i++) {
            if (bytes[i] == 0) {
                return true;
            }
        }
        return false;
    }

    static String toText(byte[] bytes) {
        String text = new String(bytes, StandardCharsets.UTF_8);
        return text.startsWith("﻿") ? text.substring(1) : text; // bỏ BOM nếu có
    }

    private static RepositoryInfo toRepositoryInfo(GitHubRepoDetails d) {
        int slash = d.fullName().indexOf('/');
        String owner = d.owner() != null && d.owner().login() != null
                ? d.owner().login()
                : slash > 0 ? d.fullName().substring(0, slash) : d.fullName();
        return new RepositoryInfo(d.id(), d.fullName(), owner, d.name(), d.description(),
                d.privateRepo(), d.archived(), d.defaultBranch(), d.htmlUrl(),
                d.language(), d.size(), d.pushedAt());
    }

    static CommitInfo toCommitInfo(GitHubCommit c) {
        GitHubCommit.Detail detail = c.commit();
        GitHubCommit.Person author = detail != null ? detail.author() : null;
        GitHubCommit.Person committer = detail != null ? detail.committer() : null;
        Instant date = author != null && author.date() != null
                ? author.date()
                : committer != null ? committer.date() : null;
        return new CommitInfo(
                c.sha(),
                detail != null ? detail.message() : null,
                author != null ? author.name() : null,
                c.author() != null ? c.author().login() : null,
                date,
                c.htmlUrl());
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static String shortSha(String sha) {
        return sha != null && sha.length() > 7 ? sha.substring(0, 7) : sha;
    }
}
