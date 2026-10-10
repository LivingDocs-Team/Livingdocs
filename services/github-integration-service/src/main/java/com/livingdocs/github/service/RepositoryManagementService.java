package com.livingdocs.github.service;

import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubRepo;
import com.livingdocs.github.dto.AvailableRepositoryResponse;
import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Epic 3 - chọn repo từ GitHub, thêm vào workspace, xem, đồng bộ, ngắt kết nối. */
@Service
public class RepositoryManagementService {

    private final GitHubConnectionService connectionService;
    private final GitHubClient gitHubClient;
    private final ConnectedRepositoryRepository repositoryRepository;

    public RepositoryManagementService(GitHubConnectionService connectionService,
                                       GitHubClient gitHubClient,
                                       ConnectedRepositoryRepository repositoryRepository) {
        this.connectionService = connectionService;
        this.gitHubClient = gitHubClient;
        this.repositoryRepository = repositoryRepository;
    }

    /** Các repo người dùng có thể thêm (là các repo đã chọn khi cài GitHub App). */
    public List<AvailableRepositoryResponse> listAvailable(String userId) {
        return fetchAccessibleRepos(userId).stream()
                .map(r -> new AvailableRepositoryResponse(r.id(), r.fullName(), r.privateRepo(),
                        r.defaultBranch(), r.htmlUrl()))
                .toList();
    }

    @Transactional(noRollbackFor = ApiException.class)
    public List<RepositoryResponse> addRepositories(String userId, String workspaceId, List<Long> githubRepoIds) {
        GitHubConnection connection = connectionService.getActiveConnection(userId);
        Map<Long, GitHubRepo> accessible = fetchAccessibleRepos(userId).stream()
                .collect(Collectors.toMap(GitHubRepo::id, Function.identity(), (a, b) -> a));

        List<RepositoryResponse> added = new ArrayList<>();
        for (Long repoId : githubRepoIds.stream().distinct().toList()) {
            GitHubRepo repo = accessible.get(repoId);
            if (repo == null) {
                throw ApiException.badRequest("Repository " + repoId
                        + " không nằm trong danh sách repo mà GitHub App được phép truy cập.");
            }
            if (repositoryRepository.existsByWorkspaceIdAndGithubRepoId(workspaceId, repoId)) {
                continue; // đã thêm rồi thì bỏ qua
            }
            ConnectedRepository entity = new ConnectedRepository();
            entity.setWorkspaceId(workspaceId);
            entity.setConnectionId(connection.getId());
            entity.setGithubRepoId(repo.id());
            entity.setFullName(repo.fullName());
            entity.setDefaultBranch(repo.defaultBranch());
            entity.setPrivateRepo(repo.privateRepo());
            entity.setHtmlUrl(repo.htmlUrl());
            entity.setStatus(RepositoryStatus.CONNECTED);
            entity.setLastSyncedAt(Instant.now());
            added.add(RepositoryResponse.from(repositoryRepository.save(entity)));
        }
        return added;
    }

    @Transactional(readOnly = true)
    public List<RepositoryResponse> listByWorkspace(String workspaceId) {
        return repositoryRepository.findByWorkspaceIdOrderByFullNameAsc(workspaceId).stream()
                .map(RepositoryResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public RepositoryResponse get(UUID id) {
        return RepositoryResponse.from(find(id));
    }

    @Transactional
    public void disconnect(String userId, UUID id) {
        ConnectedRepository repo = find(id);
        checkOwner(userId, repo);
        repositoryRepository.delete(repo);
    }

    /**
     * Đồng bộ thủ công: lấy lại thông tin repo từ GitHub (nhánh mặc định...) và cập nhật thời gian đồng bộ.
     * Sprint sau sẽ mở rộng để kéo cả Pull Request và commit.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public RepositoryResponse sync(String userId, UUID id) {
        ConnectedRepository repo = find(id);
        checkOwner(userId, repo);
        GitHubConnection connection = connectionService.getActiveConnection(userId);
        try {
            GitHubRepo latest = gitHubClient.getRepository(connection.getAccessToken(), repo.getFullName());
            repo.setFullName(latest.fullName());
            repo.setDefaultBranch(latest.defaultBranch());
            repo.setPrivateRepo(latest.privateRepo());
            repo.setHtmlUrl(latest.htmlUrl());
            repo.setStatus(RepositoryStatus.CONNECTED);
            repo.setLastSyncedAt(Instant.now());
        } catch (GitHubApiException e) {
            if (e.isUnauthorized()) {
                connectionService.markInvalid(connection);
                throw ApiException.githubReauthRequired();
            }
            repo.setStatus(RepositoryStatus.ERROR);
            repositoryRepository.save(repo);
            throw e;
        }
        return RepositoryResponse.from(repositoryRepository.save(repo));
    }

    private List<GitHubRepo> fetchAccessibleRepos(String userId) {
        GitHubConnection connection = connectionService.getActiveConnection(userId);
        try {
            return gitHubClient.listAccessibleRepositories(connection.getAccessToken());
        } catch (GitHubApiException e) {
            if (e.isUnauthorized()) {
                connectionService.markInvalid(connection);
                throw ApiException.githubReauthRequired();
            }
            throw e;
        }
    }

    private ConnectedRepository find(UUID id) {
        return repositoryRepository.findById(id)
                .orElseThrow(() -> ApiException.notFound("Không tìm thấy repository " + id));
    }

    private void checkOwner(String userId, ConnectedRepository repo) {
        GitHubConnection connection = connectionService.findConnection(userId).orElse(null);
        if (connection == null || !connection.getId().equals(repo.getConnectionId())) {
            throw ApiException.forbidden("Repository này không thuộc kết nối GitHub của bạn.");
        }
    }
}
