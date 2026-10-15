package com.livingdocs.github.sync;

import java.util.Locale;
import java.util.Set;

/**
 * Quyết định file nào KHÔNG cần đồng bộ: thư viện bên thứ ba, file build sinh ra,
 * file cấu hình IDE, file đã minify, và đường dẫn bất thường.
 */
public final class PathFilter {

    /** Luôn bỏ qua, ở bất kỳ đâu trong đường dẫn. */
    private static final Set<String> ALWAYS_IGNORED = Set.of(
            ".git", ".github", ".idea", ".vscode", ".gradle", ".mvn",
            "node_modules", "bower_components",
            "venv", ".venv", "__pycache__", ".pytest_cache", ".tox", "site-packages",
            ".next", ".nuxt");

    /**
     * Thư mục kết quả build. Chỉ bỏ qua khi nằm NGOÀI thư mục "src",
     * để không loại nhầm package Java hợp lệ như src/main/java/com/acme/build/Builder.java.
     */
    private static final Set<String> BUILD_OUTPUT = Set.of(
            "target", "build", "dist", "out", "bin", "obj", "vendor", "coverage");

    private PathFilter() {
    }

    /** true nếu file nằm trong thư mục bị bỏ qua hoặc là file sinh tự động / đường dẫn không an toàn. */
    public static boolean isIgnored(String path) {
        if (!isSafe(path)) {
            return true;
        }
        String[] segments = path.split("/");
        boolean insideSrc = false;
        for (int i = 0; i < segments.length - 1; i++) { // chỉ xét thư mục, không xét tên file
            String dir = segments[i].toLowerCase(Locale.ROOT);
            if (ALWAYS_IGNORED.contains(dir)) {
                return true;
            }
            if (!insideSrc && BUILD_OUTPUT.contains(dir)) {
                return true;
            }
            if (dir.equals("src")) {
                insideSrc = true;
            }
        }
        String fileName = segments[segments.length - 1].toLowerCase(Locale.ROOT);
        return fileName.endsWith(".min.js") || fileName.endsWith(".bundle.js");
    }

    /** Chặn đường dẫn rỗng, tuyệt đối, có "..", "\" hoặc ký tự điều khiển. */
    public static boolean isSafe(String path) {
        if (path == null || path.isBlank() || path.startsWith("/") || path.contains("\\")) {
            return false;
        }
        for (String segment : path.split("/", -1)) {
            if (segment.isEmpty() || segment.equals(".") || segment.equals("..")) {
                return false;
            }
        }
        for (int i = 0; i < path.length(); i++) {
            if (Character.isISOControl(path.charAt(i))) {
                return false;
            }
        }
        return true;
    }
}
