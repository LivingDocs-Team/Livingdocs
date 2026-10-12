package com.livingdocs.github.sync;

import com.livingdocs.github.client.GitHubBlob;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubCommit;
import com.livingdocs.github.client.GitHubRepoDetails;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.sync.RepositorySnapshot.SkipReason;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Test logic đồng bộ với GitHub giả (mock): không cần mạng, không cần token thật.
 */
class GitHubRepositoryFetcherTest {

    private static final String TOKEN = "ghu_test_token";
    private static final String OWNER = "LivingDocs-Team";
    private static final String REPO = "Livingdocs";
    private static final String FULL_NAME = OWNER + "/" + REPO;
    private static final String HEAD_SHA = sha(1000);
    private static final String TREE_SHA = sha(2000);

    private static final String APP_JAVA = "package demo;\n\npublic class App {\n    public static void main(String[] a) {}\n}\n";
    private static final String TOOL_PY = "﻿def hello(name):\n    return 'hi ' + name\n";

    private GitHubClient client;
    private GitHubRepositoryFetcher fetcher;
    private List<GitHubTree.Entry> treeEntries;

    @BeforeEach
    void setUp() {
        client = mock(GitHubClient.class);
        fetcher = new GitHubRepositoryFetcher(client);

        treeEntries = new ArrayList<>(List.of(
                dir("src"),
                blob("src/main/java/demo/App.java", APP_JAVA.length(), sha(1)),
                blob("scripts/tool.py", TOOL_PY.length(), sha(2)),
                blob("README.md", 100, sha(3)),                              // không phải code
                blob("frontend/node_modules/lib/x.py", 50, sha(4)),          // thư viện ngoài
                blob("target/generated/Gen.java", 50, sha(5)),               // file build sinh ra
                blob("src/main/java/demo/Big.java", 300_000, sha(6)),        // quá lớn
                blob("src/main/java/demo/Weird.java", 10, sha(7)),           // nhị phân
                blob("src/main/java/com/acme/build/Builder.java", 30, sha(8)) // package "build" hợp lệ
        ));

        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenReturn(repoDetails(FULL_NAME, false, false));
        when(client.getCommit(TOKEN, OWNER, REPO, "main")).thenReturn(commit(HEAD_SHA, "Add sync", TREE_SHA));
        when(client.getTree(TOKEN, OWNER, REPO, TREE_SHA)).thenAnswer(inv -> new GitHubTree(TREE_SHA, false, treeEntries));
        when(client.getBlob(TOKEN, OWNER, REPO, sha(1))).thenReturn(textBlob(sha(1), APP_JAVA));
        when(client.getBlob(TOKEN, OWNER, REPO, sha(2))).thenReturn(textBlob(sha(2), TOOL_PY));
        when(client.getBlob(TOKEN, OWNER, REPO, sha(7))).thenReturn(binaryBlob(sha(7)));
        when(client.getBlob(TOKEN, OWNER, REPO, sha(8))).thenReturn(textBlob(sha(8), "package com.acme.build;\nclass Builder {}\n"));
        Map<String, Long> languages = new LinkedHashMap<>();
        languages.put("Java", 5000L);
        languages.put("Python", 120L);
        when(client.getLanguages(TOKEN, OWNER, REPO)).thenReturn(languages);
        when(client.listCommits(TOKEN, OWNER, REPO, "main", 20)).thenReturn(List.of(
                commit(HEAD_SHA, "Add sync", TREE_SHA),
                commit(sha(999), "Initial commit", sha(998))));
    }

    // ------------------------------------------------------------------ trường hợp thành công

    @Test
    void fetch_returnsRepositoryInfoCommitAndSourceFiles() {
        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, SyncOptions.defaults());

        assertThat(snapshot.repository().fullName()).isEqualTo(FULL_NAME);
        assertThat(snapshot.repository().owner()).isEqualTo(OWNER);
        assertThat(snapshot.repository().defaultBranch()).isEqualTo("main");
        assertThat(snapshot.branch()).isEqualTo("main");
        assertThat(snapshot.headCommit().sha()).isEqualTo(HEAD_SHA);
        assertThat(snapshot.headCommit().authorLogin()).isEqualTo("d3r-bbb");
        assertThat(snapshot.languages()).containsExactly(Map.entry("Java", 5000L), Map.entry("Python", 120L));
        assertThat(snapshot.recentCommits()).extracting(RepositorySnapshot.CommitInfo::message)
                .containsExactly("Add sync", "Initial commit");
        assertThat(snapshot.warnings()).isEmpty();

        // Chỉ lấy file java/python, sắp xếp theo đường dẫn, bỏ README, node_modules, target
        assertThat(snapshot.files()).extracting(SourceFile::path).containsExactly(
                "scripts/tool.py",
                "src/main/java/com/acme/build/Builder.java",
                "src/main/java/demo/App.java",
                "src/main/java/demo/Big.java",
                "src/main/java/demo/Weird.java");

        SourceFile app = file(snapshot, "src/main/java/demo/App.java");
        assertThat(app.language()).isEqualTo("java");
        assertThat(app.content()).isEqualTo(APP_JAVA);
        assertThat(app.skipReason()).isNull();

        SourceFile tool = file(snapshot, "scripts/tool.py");
        assertThat(tool.language()).isEqualTo("python");
        assertThat(tool.content()).startsWith("def hello").doesNotContain("﻿"); // đã bỏ BOM

        assertThat(file(snapshot, "src/main/java/demo/Big.java").skipReason()).isEqualTo(SkipReason.TOO_LARGE);
        assertThat(file(snapshot, "src/main/java/demo/Weird.java").skipReason()).isEqualTo(SkipReason.BINARY);

        assertThat(snapshot.analyzableFiles()).extracting(SourceFile::path).containsExactly(
                "scripts/tool.py", "src/main/java/com/acme/build/Builder.java", "src/main/java/demo/App.java");

        RepositorySnapshot.SyncStats stats = snapshot.stats();
        assertThat(stats.totalFilesInRepo()).isEqualTo(8);
        assertThat(stats.filesSelected()).isEqualTo(5);
        assertThat(stats.filesWithContent()).isEqualTo(3);
        assertThat(stats.filesIgnored()).isEqualTo(3);
        assertThat(stats.treeTruncated()).isFalse();
        assertThat(stats.fileLimitReached()).isFalse();

        // Không tải nội dung file quá lớn hay file không cần
        verify(client, never()).getBlob(anyString(), anyString(), anyString(), eq(sha(6)));
        verify(client, never()).getBlob(anyString(), anyString(), anyString(), eq(sha(3)));
    }

    @Test
    void fetch_withoutContent_listsFilesButDownloadsNothing() {
        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, SyncOptions.defaults().withIncludeContent(false));

        assertThat(snapshot.files()).hasSize(5)
                .allSatisfy(f -> assertThat(f.skipReason()).isEqualTo(SkipReason.NOT_REQUESTED));
        assertThat(snapshot.analyzableFiles()).isEmpty();
        verify(client, never()).getBlob(any(), any(), any(), any());
    }

    @Test
    void fetch_respectsMaxFiles() {
        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, SyncOptions.defaults().withMaxFiles(2));

        assertThat(snapshot.files()).hasSize(2);
        assertThat(snapshot.stats().fileLimitReached()).isTrue();
        assertThat(codes(snapshot)).contains("FILE_LIMIT_REACHED");
    }

    @Test
    void fetch_otherBranch() {
        when(client.getCommit(TOKEN, OWNER, REPO, "develop")).thenReturn(commit(HEAD_SHA, "Dev", TREE_SHA));
        when(client.listCommits(TOKEN, OWNER, REPO, "develop", 20)).thenReturn(List.of());

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, SyncOptions.defaults().withBranch("develop"));

        assertThat(snapshot.branch()).isEqualTo("develop");
    }

    @Test
    void fetch_archivedRepository_addsWarning() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenReturn(repoDetails(FULL_NAME, true, false));

        assertThat(codes(fetcher.fetch(TOKEN, FULL_NAME, null))).contains("ARCHIVED_REPOSITORY");
    }

    @Test
    void fetch_renamedRepository_usesNewNameAndWarns() {
        when(client.getRepositoryDetails(TOKEN, OWNER, "OldName")).thenReturn(repoDetails(FULL_NAME, false, false));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, OWNER + "/OldName", null);

        assertThat(snapshot.repository().fullName()).isEqualTo(FULL_NAME);
        assertThat(codes(snapshot)).contains("REPOSITORY_RENAMED");
        verify(client).getCommit(TOKEN, OWNER, REPO, "main"); // gọi tiếp bằng tên mới
    }

    @Test
    void fetch_truncatedTree_addsWarning() {
        when(client.getTree(TOKEN, OWNER, REPO, TREE_SHA)).thenReturn(new GitHubTree(TREE_SHA, true, treeEntries));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, null);

        assertThat(snapshot.stats().treeTruncated()).isTrue();
        assertThat(codes(snapshot)).contains("TREE_TRUNCATED");
    }

    @Test
    void fetch_noSourceFiles_addsWarning() {
        treeEntries.clear();
        treeEntries.add(blob("README.md", 10, sha(3)));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, null);

        assertThat(snapshot.files()).isEmpty();
        assertThat(codes(snapshot)).contains("NO_SOURCE_FILES");
    }

    @Test
    void fetch_unsafePathsAreSkipped() {
        treeEntries.add(blob("../evil.java", 10, sha(9)));
        treeEntries.add(blob("/abs/Evil.java", 10, sha(10)));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, null);

        assertThat(snapshot.files()).extracting(SourceFile::path).doesNotContain("../evil.java", "/abs/Evil.java");
        assertThat(codes(snapshot)).contains("UNSAFE_PATHS_SKIPPED");
    }

    @Test
    void fetch_oneFileUnavailable_otherFilesStillSynced() {
        when(client.getBlob(TOKEN, OWNER, REPO, sha(2))).thenThrow(error(404, null));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, null);

        assertThat(file(snapshot, "scripts/tool.py").skipReason()).isEqualTo(SkipReason.UNAVAILABLE);
        assertThat(file(snapshot, "src/main/java/demo/App.java").hasContent()).isTrue();
        assertThat(codes(snapshot)).contains("FILE_UNAVAILABLE");
    }

    @Test
    void fetch_languagesUnavailable_onlyWarns() {
        when(client.getLanguages(TOKEN, OWNER, REPO)).thenThrow(error(500, null));

        RepositorySnapshot snapshot = fetcher.fetch(TOKEN, FULL_NAME, null);

        assertThat(snapshot.languages()).isEmpty();
        assertThat(codes(snapshot)).contains("LANGUAGES_UNAVAILABLE");
    }

    @Test
    void zeroRecentCommits_skipsCommitHistoryCall() {
        // recentCommitLimit = 0 thì không gọi API lịch sử commit
        SyncOptions noCommits = new SyncOptions(null, false, 10, 1000, 0, null);
        fetcher.fetch(TOKEN, FULL_NAME, noCommits);
        verify(client, never()).listCommits(anyString(), anyString(), anyString(), anyString(), anyInt());
    }

    // ------------------------------------------------------------------ các lỗi

    @Test
    void invalidRepositoryName_failsWithoutCallingGitHub() {
        for (String bad : new String[]{null, "", "no-slash", "a/b/c", "../etc/passwd", "owner/..", "own er/repo", "<script>/x"}) {
            assertSyncError(() -> fetcher.fetch(TOKEN, bad, null), SyncErrorCode.INVALID_REPOSITORY);
        }
        verifyNoInteractions(client);
    }

    @Test
    void repositoryNotFound() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenThrow(error(404, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.REPOSITORY_NOT_FOUND);
    }

    @Test
    void tokenInvalid() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenThrow(error(401, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.TOKEN_INVALID);
    }

    @Test
    void accessDenied() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenThrow(error(403, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.ACCESS_DENIED);
    }

    @Test
    void disabledRepository_isAccessDenied() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenReturn(repoDetails(FULL_NAME, false, true));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.ACCESS_DENIED);
    }

    @Test
    void rateLimited_reportsRetryTime() {
        HttpHeaders headers = new HttpHeaders();
        headers.add("x-ratelimit-remaining", "0");
        headers.add("x-ratelimit-reset", "1791000000");
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO)).thenThrow(error(403, headers));

        RepositorySyncException e = assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.RATE_LIMITED);
        assertThat(e.getRetryAt()).isEqualTo(Instant.ofEpochSecond(1791000000));
        assertThat(e.getCode().retryable()).isTrue();
    }

    @Test
    void rateLimitedWhileDownloading_stopsSync() {
        when(client.getBlob(TOKEN, OWNER, REPO, sha(2))).thenThrow(error(429, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.RATE_LIMITED);
    }

    @Test
    void emptyRepository() {
        when(client.getCommit(TOKEN, OWNER, REPO, "main")).thenThrow(error(409, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.EMPTY_REPOSITORY);
    }

    @Test
    void branchNotFound() {
        when(client.getCommit(TOKEN, OWNER, REPO, "khong-co")).thenThrow(error(422, null));

        RepositorySyncException e = assertSyncError(
                () -> fetcher.fetch(TOKEN, FULL_NAME, SyncOptions.defaults().withBranch("khong-co")),
                SyncErrorCode.BRANCH_NOT_FOUND);
        assertThat(e.getMessage()).contains("khong-co");
    }

    @Test
    void networkError_isGitHubUnavailable() {
        when(client.getRepositoryDetails(TOKEN, OWNER, REPO))
                .thenThrow(new GitHubApiException("timeout", new RuntimeException("Read timed out")));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.GITHUB_UNAVAILABLE);
    }

    @Test
    void gitHubServerError_isGitHubUnavailable() {
        when(client.getTree(TOKEN, OWNER, REPO, TREE_SHA)).thenThrow(error(502, null));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.GITHUB_UNAVAILABLE);
    }

    @Test
    void malformedCommitFromGitHub_isRejectedByVerifier() {
        when(client.getCommit(TOKEN, OWNER, REPO, "main")).thenReturn(commit("not-a-sha", "x", TREE_SHA));

        assertSyncError(() -> fetcher.fetch(TOKEN, FULL_NAME, null), SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE);
    }

    @Test
    void invalidOptions_areRejected() {
        assertSyncError(() -> SyncOptions.defaults().withMaxFiles(0), SyncErrorCode.INVALID_REQUEST);
        assertSyncError(() -> SyncOptions.defaults().withMaxFileSizeBytes(0), SyncErrorCode.INVALID_REQUEST);
    }

    // ------------------------------------------------------------------ helpers

    private static RepositorySyncException assertSyncError(Runnable action, SyncErrorCode expected) {
        Throwable thrown = catchThrowable(action::run);
        assertThat(thrown).isInstanceOf(RepositorySyncException.class);
        RepositorySyncException e = (RepositorySyncException) thrown;
        assertThat(e.getCode()).isEqualTo(expected);
        assertThat(e.getMessage()).isNotBlank();
        return e;
    }

    private static List<String> codes(RepositorySnapshot snapshot) {
        return snapshot.warnings().stream().map(SyncWarning::code).toList();
    }

    private static SourceFile file(RepositorySnapshot snapshot, String path) {
        return snapshot.files().stream().filter(f -> f.path().equals(path)).findFirst().orElseThrow();
    }

    private static GitHubApiException error(int status, HttpHeaders headers) {
        return new GitHubApiException("GitHub API trả lỗi " + status, status, headers, "{\"message\":\"error\"}");
    }

    static String sha(int n) {
        return String.format("%040x", n);
    }

    private static GitHubRepoDetails repoDetails(String fullName, boolean archived, boolean disabled) {
        return new GitHubRepoDetails(101L, fullName.substring(fullName.indexOf('/') + 1), fullName,
                new GitHubRepoDetails.Owner(fullName.substring(0, fullName.indexOf('/'))),
                "LivingDocs demo", false, archived, disabled, "main",
                "https://github.com/" + fullName, "Java", 1234L, Instant.parse("2026-10-12T08:00:00Z"));
    }

    private static GitHubCommit commit(String sha, String message, String treeSha) {
        GitHubCommit.Person person = new GitHubCommit.Person("Dang Le Hien Hai", "dang@example.com",
                Instant.parse("2026-10-12T09:00:00Z"));
        return new GitHubCommit(sha, "https://github.com/" + FULL_NAME + "/commit/" + sha,
                new GitHubCommit.Detail(message, person, person, new GitHubCommit.TreeRef(treeSha)),
                new GitHubCommit.Account("d3r-bbb"));
    }

    private static GitHubTree.Entry blob(String path, long size, String sha) {
        return new GitHubTree.Entry(path, "100644", "blob", sha, size);
    }

    private static GitHubTree.Entry dir(String path) {
        return new GitHubTree.Entry(path, "040000", "tree", sha(4242), null);
    }

    private static GitHubBlob textBlob(String sha, String text) {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        return new GitHubBlob(sha, (long) bytes.length, "base64", Base64.getMimeEncoder().encodeToString(bytes));
    }

    private static GitHubBlob binaryBlob(String sha) {
        byte[] bytes = {(byte) 0x89, 'P', 'N', 'G', 0, 0, 0, 13};
        return new GitHubBlob(sha, (long) bytes.length, "base64", Base64.getEncoder().encodeToString(bytes));
    }

}
