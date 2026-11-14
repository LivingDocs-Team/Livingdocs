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
import com.livingdocs.github.repository.GitHubConnectionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/** Epic 3 - chọn repo từ GitHub, thêm vào workspace, xem, ngắt kết nối. Đồng bộ (LD-63): RepositorySyncService. */
@Service
public class RepositoryManagementService {

    private final GitHubConnectionService connectionService;
    private final GitHubClient gitHubClient;
    private final ConnectedRepositoryRepository repositoryRepository;
    private final GitHubConnectionRepository connectionRepository;

    public RepositoryManagementService(GitHubConnectionService connectionService,
                                       GitHubClient gitHubClient,
                                       ConnectedRepositoryRepository repositoryRepository,
                                       GitHubConnectionRepository connectionRepository) {
        this.connectionService = connectionService;
        this.gitHubClient = gitHubClient;
        this.repositoryRepository = repositoryRepository;
        this.connectionRepository = connectionRepository;
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
        return addRepositories(userId, workspaceId, githubRepoIds, null, "OWNER");
    }

    @Transactional(noRollbackFor = ApiException.class)
    public List<RepositoryResponse> addRepositories(String userId, String workspaceId,
            List<Long> githubRepoIds, String verifiedWorkspaceId, String verifiedAccess) {
        requireWorkspaceOwner(userId, workspaceId, verifiedWorkspaceId, verifiedAccess);
        GitHubConnection connection = connectionService.getActiveConnection(userId);
        Map<Long, GitHubRepo> accessible = fetchAccessibleRepos(connection).stream()
                .collect(Collectors.toMap(GitHubRepo::id, Function.identity(), (a, b) -> a));

        List<Long> requested = githubRepoIds.stream().distinct().toList();
        // Kiểm tra hết trước khi lưu (LD-76): có id không được cấp quyền thì không lưu repo nào.
        List<Long> notAllowed = requested.stream().filter(id -> !accessible.containsKey(id)).toList();
        if (!notAllowed.isEmpty()) {
            throw ApiException.badRequest("Repository "
                    + notAllowed.stream().map(String::valueOf).collect(Collectors.joining(", "))
                    + " không nằm trong danh sách repo mà GitHub App được phép truy cập.");
        }

        lockConnectionForAssociation(connection.getId());
        Set<Long> alreadyAssociated = requested.stream()
                .filter(repoId -> repositoryRepository.existsByWorkspaceIdAndConnectionIdAndGithubRepoId(
                        workspaceId, connection.getId(), repoId))
                .collect(Collectors.toSet());
        List<Long> conflictingInTarget = requested.stream()
                .filter(repoId -> !alreadyAssociated.contains(repoId))
                .filter(repoId -> repositoryRepository.existsByWorkspaceIdAndGithubRepoId(workspaceId, repoId))
                .toList();
        List<Long> associatedElsewhere = requested.stream()
                .filter(repoId -> !alreadyAssociated.contains(repoId))
                .filter(repoId -> repositoryRepository.existsByConnectionIdAndGithubRepoIdAndWorkspaceIdNot(
                        connection.getId(), repoId, workspaceId))
                .toList();
        if (!conflictingInTarget.isEmpty() || !associatedElsewhere.isEmpty()) {
            throw ApiException.repositoryConflict("Repository "
                    + java.util.stream.Stream.concat(conflictingInTarget.stream(), associatedElsewhere.stream())
                            .distinct().map(String::valueOf).collect(Collectors.joining(", "))
                    + " is already associated with a conflicting workspace/connection.");
        }

        List<RepositoryResponse> added = new ArrayList<>();
        for (Long repoId : requested) {
            GitHubRepo repo = accessible.get(repoId);
            if (alreadyAssociated.contains(repoId)) {
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
            entity.setLastSyncedAt(null);
            added.add(RepositoryResponse.from(repositoryRepository.save(entity)));
        }
        return added;
    }

    @Transactional(readOnly = true)
    public List<RepositoryResponse> listByWorkspace(String userId, String workspaceId) {
        return listByWorkspace(userId, workspaceId, null, "OWNER");
    }

    @Transactional(readOnly = true)
    public List<RepositoryResponse> listByWorkspace(
            String userId, String workspaceId, String verifiedWorkspaceId) {
        return listByWorkspace(userId, workspaceId, verifiedWorkspaceId, "OWNER");
    }

    @Transactional(readOnly = true)
    public List<RepositoryResponse> listByWorkspace(
            String userId, String workspaceId, String verifiedWorkspaceId, String verifiedAccess) {
        requireWorkspaceReadAccess(userId, workspaceId, verifiedWorkspaceId, verifiedAccess);
        List<ConnectedRepository> repositories;
        if ("MEMBER".equals(verifiedAccess) && workspaceId.startsWith("workspace-")) {
            repositories = repositoryRepository.findByWorkspaceIdOrderByFullNameAsc(workspaceId);
        } else {
            GitHubConnection connection = connectionService.findConnection(userId).orElse(null);
            if (connection == null) return List.of();
            repositories = repositoryRepository.findByWorkspaceIdAndConnectionIdOrderByFullNameAsc(
                    workspaceId, connection.getId());
        }
        return repositories.stream()
                .map(RepositoryResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public RepositoryResponse get(String userId, UUID id) {
        return get(userId, id, null);
    }

    @Transactional(readOnly = true)
    public RepositoryResponse get(String userId, UUID id, String verifiedWorkspaceId) {
        return get(userId, id, verifiedWorkspaceId, "OWNER");
    }

    @Transactional(readOnly = true)
    public RepositoryResponse get(String userId, UUID id, String verifiedWorkspaceId, String verifiedAccess) {
        ConnectedRepository repo = find(id);
        if ("MEMBER".equals(verifiedAccess) && repo.getWorkspaceId() != null
                && repo.getWorkspaceId().startsWith("workspace-")) {
            verifyRepositoryWorkspace(repo, verifiedWorkspaceId, verifiedAccess);
        } else {
            checkOwner(userId, repo);
            verifyRepositoryWorkspace(repo, verifiedWorkspaceId, verifiedAccess);
        }
        return RepositoryResponse.from(repo);
    }

    @Transactional(readOnly = true)
    public String getWorkspaceId(UUID id) {
        ConnectedRepository repo = find(id);
        return repo.getWorkspaceId();
    }

    @Transactional
    public void disconnect(String userId, UUID id) {
        disconnect(userId, id, null);
    }

    @Transactional
    public void disconnect(String userId, UUID id, String verifiedWorkspaceId) {
        disconnect(userId, id, verifiedWorkspaceId, "OWNER");
    }

    @Transactional
    public void disconnect(String userId, UUID id, String verifiedWorkspaceId, String verifiedAccess) {
        ConnectedRepository repo = find(id);
        checkOwner(userId, repo);
        requireWorkspaceOwner(userId, repo.getWorkspaceId(), verifiedWorkspaceId, verifiedAccess);
        verifyRepositoryWorkspace(repo, verifiedWorkspaceId, verifiedAccess);
        repositoryRepository.delete(repo);
    }

    @Transactional
    public RepositoryResponse reassignRepository(String userId, String targetWorkspaceId,
            UUID repositoryId, String verifiedTargetWorkspaceId, String verifiedSourceWorkspaceId) {
        return reassignRepository(userId, targetWorkspaceId, repositoryId,
                verifiedTargetWorkspaceId, verifiedSourceWorkspaceId, "OWNER");
    }

    @Transactional
    public RepositoryResponse reassignRepository(String userId, String targetWorkspaceId,
            UUID repositoryId, String verifiedTargetWorkspaceId, String verifiedSourceWorkspaceId,
            String verifiedAccess) {
        requireWorkspaceOwner(userId, targetWorkspaceId, verifiedTargetWorkspaceId, verifiedAccess);

        ConnectedRepository repository = find(repositoryId);
        checkOwner(userId, repository);
        lockConnectionForAssociation(repository.getConnectionId());

        repository = find(repositoryId);
        checkOwner(userId, repository);
        verifyRepositoryWorkspace(repository, verifiedSourceWorkspaceId, "OWNER");

        List<ConnectedRepository> matchingAssociations =
                repositoryRepository.findAllByConnectionIdAndGithubRepoIdOrderByCreatedAtAsc(
                        repository.getConnectionId(), repository.getGithubRepoId());
        if (matchingAssociations.size() > 1) {
            throw ApiException.repositoryConflict(
                    "Duplicate historical associations exist; an administrator must reconcile them before reassignment.");
        }
        if (matchingAssociations.isEmpty()
                || !matchingAssociations.getFirst().getId().equals(repositoryId)) {
            throw ApiException.notFound("Repository association not found.");
        }
        if (targetWorkspaceId.equals(repository.getWorkspaceId())) {
            return RepositoryResponse.from(repository);
        }
        if (repositoryRepository.existsByWorkspaceIdAndGithubRepoIdAndIdNot(
                targetWorkspaceId, repository.getGithubRepoId(), repositoryId)) {
            throw ApiException.repositoryConflict(
                    "The target workspace already contains this GitHub repository.");
        }

        repository.setWorkspaceId(targetWorkspaceId);
        return RepositoryResponse.from(repositoryRepository.save(repository));
    }

    // Đồng bộ repo với GitHub (LD-63): xem RepositorySyncService

    private List<GitHubRepo> fetchAccessibleRepos(String userId) {
        return fetchAccessibleRepos(connectionService.getActiveConnection(userId));
    }

    private List<GitHubRepo> fetchAccessibleRepos(GitHubConnection connection) {
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

    private void requireWorkspaceOwner(String userId, String workspaceId,
            String verifiedWorkspaceId, String verifiedAccess) {
        boolean personalWorkspace = ("ws-" + userId).equals(workspaceId);
        // Older trusted BFF calls carried only X-User-Id for personal workspaces.
        // Keep that contract while requiring explicit Backend verification for managed workspaces.
        boolean legacyPersonalRequest = personalWorkspace
                && verifiedWorkspaceId == null && verifiedAccess == null;
        if (!legacyPersonalRequest) requireOwnerAccess(verifiedAccess);
        boolean managedWorkspace = workspaceId != null && workspaceId.startsWith("workspace-")
                && workspaceId.equals(verifiedWorkspaceId);
        if (!personalWorkspace && !managedWorkspace) {
            throw ApiException.forbidden("Workspace này không thuộc người dùng đã xác thực.");
        }
        if (verifiedWorkspaceId != null && !workspaceId.equals(verifiedWorkspaceId)) {
            throw ApiException.forbidden("Workspace ownership was not verified by the Backend.");
        }
    }

    private void requireWorkspaceReadAccess(String userId, String workspaceId,
            String verifiedWorkspaceId, String verifiedAccess) {
        if (("ws-" + userId).equals(workspaceId)
                && verifiedWorkspaceId == null && verifiedAccess == null) return;
        if ("MEMBER".equals(verifiedAccess) && workspaceId != null
                && workspaceId.startsWith("workspace-") && workspaceId.equals(verifiedWorkspaceId)) return;
        if ("OWNER".equals(verifiedAccess) && ("ws-" + userId).equals(workspaceId)) return;
        if ("OWNER".equals(verifiedAccess) && workspaceId != null
                && workspaceId.startsWith("workspace-") && workspaceId.equals(verifiedWorkspaceId)) return;
        throw ApiException.forbidden("Workspace access was not verified by the Backend.");
    }

    private void requireOwnerAccess(String verifiedAccess) {
        if (!"OWNER".equals(verifiedAccess)) {
            throw ApiException.forbidden("Workspace owner access is required.");
        }
    }

    private void verifyRepositoryWorkspace(ConnectedRepository repository,
            String verifiedWorkspaceId, String verifiedAccess) {
        if (repository.getWorkspaceId() != null && repository.getWorkspaceId().startsWith("workspace-")
                && (!repository.getWorkspaceId().equals(verifiedWorkspaceId)
                        || !("OWNER".equals(verifiedAccess) || "MEMBER".equals(verifiedAccess)))) {
            throw ApiException.forbidden("Workspace ownership was not verified by the Backend.");
        }
        if (verifiedWorkspaceId != null && !repository.getWorkspaceId().equals(verifiedWorkspaceId)) {
            throw ApiException.forbidden("Repository is not associated with the verified workspace.");
        }
    }

    private void lockConnectionForAssociation(UUID connectionId) {
        connectionRepository.findByIdForUpdate(connectionId)
                .orElseThrow(ApiException::githubNotConnected);
    }
}



