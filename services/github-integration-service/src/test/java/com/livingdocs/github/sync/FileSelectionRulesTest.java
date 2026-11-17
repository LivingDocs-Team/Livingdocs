package com.livingdocs.github.sync;

import org.junit.jupiter.api.Test;

import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class FileSelectionRulesTest {

    @Test
    void detectsLanguageByExtension() {
        assertThat(LanguageDetector.detect("src/main/java/App.java")).isEqualTo("java");
        assertThat(LanguageDetector.detect("app/main.py")).isEqualTo("python");
        assertThat(LanguageDetector.detect("APP/MAIN.PY")).isEqualTo("python");
        assertThat(LanguageDetector.detect("web/index.tsx")).isEqualTo("typescript");
        assertThat(LanguageDetector.detect("README.md")).isNull();
        assertThat(LanguageDetector.detect(".gitignore")).isNull();
        assertThat(LanguageDetector.detect("Makefile")).isNull();
        assertThat(LanguageDetector.detect("weird.")).isNull();
        assertThat(LanguageDetector.detect(null)).isNull();
    }

    @Test
    void ignoresDependenciesAndBuildOutput() {
        assertThat(PathFilter.isIgnored("frontend/node_modules/react/index.js")).isTrue();
        assertThat(PathFilter.isIgnored("ai-service/venv/lib/site.py")).isTrue();
        assertThat(PathFilter.isIgnored("app/__pycache__/x.py")).isTrue();
        assertThat(PathFilter.isIgnored("backend/target/classes/App.java")).isTrue();
        assertThat(PathFilter.isIgnored("build/generated/Thing.java")).isTrue();
        assertThat(PathFilter.isIgnored("static/app.min.js")).isTrue();
    }

    @Test
    void keepsRealSourceCode() {
        assertThat(PathFilter.isIgnored("backend/src/main/java/com/cnpm/backend/BackendApplication.java")).isFalse();
        assertThat(PathFilter.isIgnored("ai-service/app/generator.py")).isFalse();
        // package Java tên "build" nằm trong src thì vẫn là code thật
        assertThat(PathFilter.isIgnored("src/main/java/com/acme/build/Builder.java")).isFalse();
        // file tên "build.py" không phải thư mục build
        assertThat(PathFilter.isIgnored("scripts/build.py")).isFalse();
    }

    @Test
    void rejectsUnsafePaths() {
        assertThat(PathFilter.isSafe("src/App.java")).isTrue();
        assertThat(PathFilter.isSafe("../App.java")).isFalse();
        assertThat(PathFilter.isSafe("src/../../etc/passwd")).isFalse();
        assertThat(PathFilter.isSafe("/etc/passwd")).isFalse();
        assertThat(PathFilter.isSafe("src\\App.java")).isFalse();
        assertThat(PathFilter.isSafe("src//App.java")).isFalse();
        assertThat(PathFilter.isSafe("src/")).isFalse();
        assertThat(PathFilter.isSafe("src/A\u0000pp.java")).isFalse();
        assertThat(PathFilter.isSafe("")).isFalse();
        assertThat(PathFilter.isSafe(null)).isFalse();
    }

    @Test
    void syncOptionsNormalizeInput() {
        SyncOptions options = new SyncOptions("  ", true, 50, 1000, 5, Set.of(" JAVA ", "Python"));
        assertThat(options.branch()).isNull();
        assertThat(options.languages()).containsExactlyInAnyOrder("java", "python");

        assertThat(SyncOptions.defaults().languages()).containsExactlyInAnyOrder("java", "python");
        assertThat(SyncOptions.defaults().maxFiles()).isEqualTo(SyncOptions.DEFAULT_MAX_FILES);
        assertThat(new SyncOptions(null, true, 1, 1, 0, null).languages()).isEqualTo(SyncOptions.ANALYZER_LANGUAGES);
    }
}
