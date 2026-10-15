package com.livingdocs.github.sync;

import com.livingdocs.github.sync.RepositorySnapshot.RepositoryInfo;
import com.livingdocs.github.sync.RepositorySnapshot.SourceFile;
import com.livingdocs.github.sync.RepositorySnapshot.SyncStats;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Kiểm tra dữ liệu đồng bộ trước khi trả về (phân công LD-63: "Kiểm tra thông tin repository
 * và dữ liệu đồng bộ trả về").
 *
 * Lỗi nghiêm trọng (dữ liệu sai, không dùng được) thì ném UNEXPECTED_GITHUB_RESPONSE.
 * Điều bất thường nhưng vẫn dùng được (ví dụ repo đã đổi tên) thì thêm cảnh báo.
 */
final class SnapshotVerifier {

    /** SHA Git: 40 ký tự hex (SHA-1) hoặc 64 ký tự (SHA-256). */
    private static final Pattern GIT_SHA = Pattern.compile("^[0-9a-f]{40}([0-9a-f]{24})?$");

    private SnapshotVerifier() {
    }

    static RepositorySnapshot verify(String requestedFullName, RepositorySnapshot snapshot) {
        List<SyncWarning> extraWarnings = new ArrayList<>();

        RepositoryInfo repo = snapshot.repository();
        if (repo == null || repo.githubRepoId() == null || isBlank(repo.fullName())) {
            fail("thiếu thông tin repository");
        }
        if (!repo.fullName().equalsIgnoreCase(requestedFullName)) {
            extraWarnings.add(new SyncWarning("REPOSITORY_RENAMED",
                    "Repository đã đổi tên từ " + requestedFullName + " thành " + repo.fullName()
                            + ". Nên cập nhật tên mới trong LivingDocs."));
        }
        if (isBlank(snapshot.branch())) {
            fail("thiếu tên nhánh");
        }
        if (snapshot.headCommit() == null || !isSha(snapshot.headCommit().sha())) {
            fail("SHA của commit mới nhất không hợp lệ");
        }

        Set<String> paths = new HashSet<>();
        int withContent = 0;
        for (SourceFile file : snapshot.files()) {
            if (!PathFilter.isSafe(file.path())) {
                fail("đường dẫn file không an toàn: " + file.path());
            }
            if (!paths.add(file.path())) {
                fail("file bị trùng: " + file.path());
            }
            if (!isSha(file.sha())) {
                fail("SHA của file không hợp lệ: " + file.path());
            }
            if (isBlank(file.language())) {
                fail("thiếu ngôn ngữ của file: " + file.path());
            }
            if (file.size() < 0) {
                fail("kích thước file âm: " + file.path());
            }
            // Có nội dung thì không được có lý do bỏ qua, và ngược lại
            if (file.hasContent() == (file.skipReason() != null)) {
                fail("trạng thái nội dung không nhất quán: " + file.path());
            }
            if (file.hasContent()) {
                withContent++;
            }
        }

        SyncStats stats = snapshot.stats();
        if (stats == null
                || stats.filesSelected() != snapshot.files().size()
                || stats.filesWithContent() != withContent
                || stats.totalFilesInRepo() < stats.filesSelected()) {
            fail("thống kê không khớp với danh sách file");
        }

        if (extraWarnings.isEmpty()) {
            return snapshot;
        }
        List<SyncWarning> allWarnings = new ArrayList<>(snapshot.warnings());
        allWarnings.addAll(extraWarnings);
        return new RepositorySnapshot(snapshot.repository(), snapshot.branch(), snapshot.headCommit(),
                snapshot.languages(), snapshot.files(), snapshot.recentCommits(), stats,
                allWarnings, snapshot.fetchedAt());
    }

    private static boolean isSha(String value) {
        return value != null && GIT_SHA.matcher(value).matches();
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static void fail(String reason) {
        throw new RepositorySyncException(SyncErrorCode.UNEXPECTED_GITHUB_RESPONSE,
                "Dữ liệu đồng bộ không hợp lệ: " + reason + ".");
    }
}
