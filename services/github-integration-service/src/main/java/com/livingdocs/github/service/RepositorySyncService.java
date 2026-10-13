package com.livingdocs.github.service;

import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.sync.GitHubRepositoryFetcher;
import com.livingdocs.github.sync.RepositorySnapshot;
import com.livingdocs.github.sync.RepositorySyncException;
import com.livingdocs.github.sync.SyncErrorCode;
import com.livingdocs.github.sync.SyncOptions;
import org.springframework.stereotype.Service;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * LD-63 - đồng bộ repository với GitHub: lấy dữ liệu bằng {@link GitHubRepositoryFetcher},
 * cập nhật thông tin repo, trạng thái và thời điểm đồng bộ (LD-66), giữ kết quả lần đồng bộ gần nhất.
 *
 * Không bọc cả hàm trong một transaction vì gọi GitHub có thể mất vài chục giây:
 * mỗi lần lưu repo là một transaction ngắn, nhờ vậy trạng thái SYNCING hiện ra ngay trong lúc đồng bộ.
 */
@Service
public class RepositorySyncService {

    /** Lỗi cho thấy repo không còn đọc được nữa. Lỗi khác (tạm thời, sai tham số, token hỏng) giữ nguyên trạng thái cũ. */
    private static final Set<SyncErrorCode> MARKS_REPOSITORY_ERROR = EnumSet.of(
            SyncErrorCode.REPOSITORY_NOT_FOUND,
            SyncErrorCode.ACCESS_DENIED,
            SyncErrorCode.INVALID_REPOSITORY);

    private final ConnectedRepositoryRepository repositoryRepository;
    private final GitHubConnectionService connectionService;
    private final GitHubRepositoryFetcher fetcher;
    /** Kết quả đồng bộ gần nhất của từng repo, giữ trong bộ nhớ (mất khi khởi động lại service). */
    private final Map<UUID, RepositorySnapshot> latestResults = new ConcurrentHashMap<>();

    public RepositorySyncService(ConnectedRepositoryRepository repositoryRepository,
                                 GitHubConnectionService connectionService,
                                 GitHubRepositoryFetcher fetcher) {
        this.repositoryRepository = repositoryRepository;
        this.connectionService = connectionService;
        this.fetcher = fetcher;
    }

    /** Đồng bộ repo với GitHub. Lỗi GitHub được ném ra dạng {@link RepositorySyncException} (GlobalExceptionHandler trả JSON). */
    public RepositorySnapshot sync(String userId, UUID repositoryId, SyncOptions options) {
        ConnectedRepository repo = findOwned(userId, repositoryId);
        GitHubConnection connection = connectionService.getActiveConnection(userId); // tự làm mới token nếu sắp hết hạn

        // Lần đồng bộ trước bị dừng giữa chừng thì không khôi phục về SYNCING
        RepositoryStatus previous = repo.getStatus() == RepositoryStatus.SYNCING
                ? RepositoryStatus.CONNECTED : repo.getStatus();
        repo.setStatus(RepositoryStatus.SYNCING);
        repo = repositoryRepository.save(repo);

        try {
            RepositorySnapshot snapshot = fetcher.fetch(connection.getAccessToken(), repo.getFullName(), options);
            RepositorySnapshot.RepositoryInfo info = snapshot.repository();
            repo.setFullName(info.fullName());          // repo có thể vừa đổi tên trên GitHub
            repo.setDefaultBranch(info.defaultBranch());
            repo.setPrivateRepo(info.privateRepo());
            repo.setHtmlUrl(info.htmlUrl());
            repo.setStatus(RepositoryStatus.CONNECTED);
            repo.setLastSyncedAt(snapshot.fetchedAt());  // LD-66
            repositoryRepository.save(repo);
            latestResults.put(repositoryId, snapshot);
            return snapshot;
        } catch (RepositorySyncException e) {
            if (e.getCode() == SyncErrorCode.TOKEN_INVALID) {
                connectionService.markInvalid(connection);  // giao diện sẽ nhắc người dùng kết nối lại GitHub
            }
            repo.setStatus(MARKS_REPOSITORY_ERROR.contains(e.getCode()) ? RepositoryStatus.ERROR : previous);
            repositoryRepository.save(repo);
            throw e;
        } catch (RuntimeException e) {
            repo.setStatus(previous);
            repositoryRepository.save(repo);
            throw e;
        }
    }

    /** Kết quả lần đồng bộ gần nhất (có cả nội dung file). Chưa đồng bộ lần nào thì báo 404. */
    public RepositorySnapshot latest(String userId, UUID repositoryId) {
        findOwned(userId, repositoryId);
        RepositorySnapshot snapshot = latestResults.get(repositoryId);
        if (snapshot == null) {
            throw ApiException.notFound("Repository này chưa được đồng bộ lần nào (hoặc service vừa khởi động lại). "
                    + "Hãy gọi POST /api/repositories/" + repositoryId + "/sync trước.");
        }
        return snapshot;
    }

    /** Repo phải tồn tại và thuộc kết nối GitHub của người dùng (kết quả đồng bộ có cả nội dung code). */
    private ConnectedRepository findOwned(String userId, UUID repositoryId) {
        ConnectedRepository repo = repositoryRepository.findById(repositoryId)
                .orElseThrow(() -> ApiException.notFound("Không tìm thấy repository " + repositoryId));
        GitHubConnection connection = connectionService.findConnection(userId).orElse(null);
        if (connection == null || !connection.getId().equals(repo.getConnectionId())) {
            throw ApiException.forbidden("Repository này không thuộc kết nối GitHub của bạn.");
        }
        return repo;
    }
}
