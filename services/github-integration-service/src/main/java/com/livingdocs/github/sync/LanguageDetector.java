package com.livingdocs.github.sync;

import java.util.Locale;
import java.util.Map;

/**
 * Nhận diện ngôn ngữ lập trình theo đuôi file.
 * Giá trị trả về viết thường, khớp với tham số "language" của service phân tích code.
 */
public final class LanguageDetector {

    private static final Map<String, String> BY_EXTENSION = Map.ofEntries(
            Map.entry("java", "java"),
            Map.entry("py", "python"),
            Map.entry("js", "javascript"),
            Map.entry("jsx", "javascript"),
            Map.entry("mjs", "javascript"),
            Map.entry("cjs", "javascript"),
            Map.entry("ts", "typescript"),
            Map.entry("tsx", "typescript"),
            Map.entry("kt", "kotlin"),
            Map.entry("kts", "kotlin"),
            Map.entry("go", "go"),
            Map.entry("rb", "ruby"),
            Map.entry("php", "php"),
            Map.entry("cs", "csharp"),
            Map.entry("c", "c"),
            Map.entry("h", "c"),
            Map.entry("cpp", "cpp"),
            Map.entry("cc", "cpp"),
            Map.entry("cxx", "cpp"),
            Map.entry("hpp", "cpp"),
            Map.entry("rs", "rust"),
            Map.entry("swift", "swift"),
            Map.entry("scala", "scala"),
            Map.entry("sql", "sql"));

    private LanguageDetector() {
    }

    /** Trả về ngôn ngữ (ví dụ "java"), hoặc null nếu không phải file code được nhận diện. */
    public static String detect(String path) {
        if (path == null || path.isBlank()) {
            return null;
        }
        String fileName = path.substring(path.lastIndexOf('/') + 1);
        int dot = fileName.lastIndexOf('.');
        if (dot <= 0 || dot == fileName.length() - 1) {
            return null; // không có đuôi, hoặc file ẩn kiểu ".gitignore"
        }
        String extension = fileName.substring(dot + 1).toLowerCase(Locale.ROOT);
        return BY_EXTENSION.get(extension);
    }
}
