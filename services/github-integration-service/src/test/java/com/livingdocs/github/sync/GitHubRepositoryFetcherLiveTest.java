package com.livingdocs.github.sync;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.web.client.RestClient;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Chạy thử đồng bộ với GitHub THẬT trên một repository mẫu, để tự kiểm tra dữ liệu trả về.
 *
 * Mặc định test này bị tắt (CI và "Run All Tests" sẽ bỏ qua). Muốn chạy:
 *   IntelliJ: chuột phải file này → More Run/Debug → Modify Run Configuration...
 *   → Environment variables: GITHUB_LIVE_TEST=true
 *
 * Tuỳ chọn:
 *   GITHUB_LIVE_REPO=owner/repo   (mặc định LivingDocs-Team/Livingdocs, là repo public)
 *   GITHUB_TOKEN=...              (không bắt buộc với repo public; không có token thì GitHub cho 60 lần gọi/giờ)
 */
@EnabledIfEnvironmentVariable(named = "GITHUB_LIVE_TEST", matches = "true")
class GitHubRepositoryFetcherLiveTest {

    @Test
    void fetchSampleRepository() throws Exception {
        GitHubProperties props = new GitHubProperties(null, null, null, null,
                "https://github.com", "https://api.github.com");
        GitHubRepositoryFetcher fetcher = new GitHubRepositoryFetcher(new GitHubClient(props, RestClient.builder()));

        String repo = envOrDefault("GITHUB_LIVE_REPO", "LivingDocs-Team/Livingdocs");
        String token = System.getenv("GITHUB_TOKEN");

        RepositorySnapshot snapshot = fetcher.fetch(token, repo, SyncOptions.defaults().withMaxFiles(25));

        System.out.println("=== Repository: " + snapshot.repository().fullName()
                + " @ " + snapshot.branch() + " (" + snapshot.headCommit().sha() + ")");
        System.out.println("=== Commit: " + snapshot.headCommit().message());
        System.out.println("=== Languages: " + snapshot.languages());
        System.out.println("=== Stats: " + snapshot.stats());
        System.out.println("=== Warnings: " + snapshot.warnings());
        for (SourceFile f : snapshot.files()) {
            System.out.printf("  %-8s %7d B  %-70s %s%n", f.language(), f.size(), f.path(),
                    f.hasContent() ? "OK" : f.skipReason());
        }

        // In JSON (rút gọn nội dung file) để gửi Minh xem cấu trúc thật
        ObjectMapper json = new ObjectMapper().findAndRegisterModules()
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(SerializationFeature.INDENT_OUTPUT);
        List<SourceFile> preview = snapshot.files().stream().limit(3)
                .map(f -> new SourceFile(f.path(), f.sha(), f.size(), f.language(),
                        f.content() == null ? null : f.content().substring(0, Math.min(80, f.content().length())) + "...",
                        f.skipReason()))
                .toList();
        RepositorySnapshot shortened = new RepositorySnapshot(snapshot.repository(), snapshot.branch(),
                snapshot.headCommit(), snapshot.languages(), preview, snapshot.recentCommits().stream().limit(2).toList(),
                snapshot.stats(), snapshot.warnings(), snapshot.fetchedAt());
        System.out.println(json.writeValueAsString(shortened));

        assertThat(snapshot.headCommit().sha()).hasSize(40);
        assertThat(snapshot.files()).isNotEmpty();
        assertThat(snapshot.analyzableFiles()).isNotEmpty();
    }

    private static String envOrDefault(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
