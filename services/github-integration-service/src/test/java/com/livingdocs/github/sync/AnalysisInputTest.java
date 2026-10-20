package com.livingdocs.github.sync;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.sync.RepositorySnapshot.SkipReason;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AnalysisInputTest {

    @Test
    void keepsOnlyFilesWithContent() {
        AnalysisInput input = AnalysisInput.from(snapshot(List.of(
                new SourceFile("app/main.py", "1".repeat(40), 20, "python", "print('hi')\n", null),
                new SourceFile("src/Big.java", "2".repeat(40), 900_000, "java", null, SkipReason.TOO_LARGE),
                new SourceFile("src/App.java", "3".repeat(40), 12, "java", "class App {}", null))));

        assertThat(input.scope()).isEqualTo("repository");
        assertThat(input.target()).isEqualTo("acme/shop");
        assertThat(input.files()).containsExactly(
                new AnalysisInput.FileInput("app/main.py", "python", "print('hi')\n"),
                new AnalysisInput.FileInput("src/App.java", "java", "class App {}"));
    }

    /** Tên field phải khớp với body mà POST /api/v1/analyze-repo (LD-328) nhận. */
    @Test
    void jsonMatchesWhatAnalysisServiceExpects() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        AnalysisInput input = AnalysisInput.from(snapshot(List.of(
                new SourceFile("src/App.java", "3".repeat(40), 12, "java", "class App {}", null))));

        JsonNode actual = mapper.valueToTree(input);
        JsonNode expected = mapper.readTree("""
                {"scope": "repository", "target": "acme/shop",
                 "files": [{"path": "src/App.java", "language": "java", "content": "class App {}"}]}""");

        assertThat(actual).isEqualTo(expected);
    }

    private static RepositorySnapshot snapshot(List<SourceFile> files) {
        return new RepositorySnapshot(
                new RepositorySnapshot.RepositoryInfo(1L, "acme/shop", "acme", "shop", null, false, false,
                        "main", "https://github.com/acme/shop", "Java", 10L, null),
                "main",
                new RepositorySnapshot.CommitInfo("a".repeat(40), "init", null, null, null, null),
                Map.of(), files, List.of(),
                new RepositorySnapshot.SyncStats(files.size(), files.size(), 0, 0, false, false),
                List.of(), Instant.now());
    }
}
