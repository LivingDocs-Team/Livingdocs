package com.livingdocs.github.service;

import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubTokenResponse;
import com.livingdocs.github.client.GitHubUser;
import com.livingdocs.github.config.GitHubProperties;
import com.livingdocs.github.dto.AuthorizeUrlResponse;
import com.livingdocs.github.dto.ConnectionResponse;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.security.OAuthStateStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.util.UriComponentsBuilder;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.locks.ReentrantLock;

/** Epic 2 - kết nối, xem trạng thái và thu hồi kết nối GitHub. */
@Service
public class GitHubConnectionService {

    private static final Logger log = LoggerFactory.getLogger(GitHubConnectionService.class);
    /** Làm mới token sớm 5 phút trước khi hết hạn. */
    private static final Duration REFRESH_MARGIN = Duration.ofMinutes(5);

    private final GitHubProperties props;
    private final GitHubClient gitHubClient;
    private final OAuthStateStore stateStore;
    private final GitHubConnectionRepository connectionRepository;
    private final ConnectedRepositoryRepository repositoryRepository;
    /**
     * Làm mới token trong một transaction riêng (LD-76): token mới được lưu xong
     * trước khi request khác của cùng user đọc lại kết nối.
     */
    private final TransactionTemplate newTransaction;
    /**
     * Mỗi user một khoá (LD-76): refresh token của GitHub App chỉ dùng được một lần,
     * hai request làm mới song song thì request sau nhận bad_refresh_token.
     */
    private final ConcurrentMap<String, ReentrantLock> refreshLocks = new ConcurrentHashMap<>();

    public GitHubConnectionService(GitHubProperties props,
                                   GitHubClient gitHubClient,
                                   OAuthStateStore stateStore,
                                   GitHubConnectionRepository connectionRepository,
                                   ConnectedRepositoryRepository repositoryRepository,
                                   PlatformTransactionManager transactionManager) {
        this.props = props;
        this.gitHubClient = gitHubClient;
        this.stateStore = stateStore;
        this.connectionRepository = connectionRepository;
        this.repositoryRepository = repositoryRepository;
        this.newTransaction = new TransactionTemplate(transactionManager);
        this.newTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public AuthorizeUrlResponse createAuthorizeUrl(String userId) {
        String state = stateStore.create(userId);
        String authorizeUrl = UriComponentsBuilder.fromUriString(props.oauthBaseUrl())
                .path("/login/oauth/authorize")
                .queryParam("client_id", props.clientId())
                .queryParam("redirect_uri", props.redirectUri())
                .queryParam("state", state)
                .encode()
                .toUriString();
        String installUrl = UriComponentsBuilder.fromUriString(props.oauthBaseUrl())
                .path("/apps/{slug}/installations/new")
                .queryParam("state", state)
                .buildAndExpand(props.appSlug())
                .encode()
                .toUriString();
        return new AuthorizeUrlResponse(authorizeUrl, installUrl, state);
    }

    /** GitHub gọi về đây sau khi người dùng bấm "Authorize" (hoặc cài app xong). */
    @Transactional
    public GitHubConnection handleCallback(String code, String state) {
        if (code == null || code.isBlank()) {
            throw ApiException.badRequest("Thiếu tham số code từ GitHub.");
        }
        String userId = stateStore.consume(state).orElseThrow(() -> ApiException.badRequest(
                "State không hợp lệ hoặc đã hết hạn. Hãy bấm 'Kết nối GitHub' lại từ đầu."));

        GitHubTokenResponse token = gitHubClient.exchangeCode(code);
        GitHubUser user = gitHubClient.getAuthenticatedUser(token.accessToken());

        GitHubConnection connection = connectionRepository.findByUserId(userId).orElseGet(GitHubConnection::new);
        boolean otherAccount = connection.getGithubUserId() != null
                && !connection.getGithubUserId().equals(user.id());
        connection.setUserId(userId);
        connection.setGithubUserId(user.id());
        connection.setGithubLogin(user.login());
        applyToken(connection, token);
        connection.setStatus(ConnectionStatus.ACTIVE);
        GitHubConnection saved = connectionRepository.save(connection);
        updateRepositoriesAfterReconnect(saved, otherAccount);
        log.info("User {} connected GitHub account {}", userId, user.login());
        return saved;
    }

    @Transactional(readOnly = true)
    public ConnectionResponse getStatus(String userId) {
        return connectionRepository.findByUserId(userId)
                .map(c -> {
                    ConnectionStatus status = effectiveStatus(c);
                    return new ConnectionResponse(
                            status == ConnectionStatus.ACTIVE,
                            c.getGithubLogin(),
                            status.name(),
                            c.getCreatedAt(),
                            c.getAccessTokenExpiresAt());
                })
                .orElseGet(ConnectionResponse::notConnected);
    }

    /** Ngắt kết nối: thu hồi quyền trên GitHub, xoá token, đánh dấu các repo là DISCONNECTED. */
    @Transactional
    public void revoke(String userId) {
        GitHubConnection connection = connectionRepository.findByUserId(userId)
                .orElseThrow(() -> ApiException.notFound("Bạn chưa kết nối GitHub."));
        if (connection.getAccessToken() != null) {
            gitHubClient.revokeGrant(connection.getAccessToken());
        }
        connection.setAccessToken(null);
        connection.setRefreshToken(null);
        connection.setAccessTokenExpiresAt(null);
        connection.setStatus(ConnectionStatus.REVOKED);
        connectionRepository.save(connection);

        for (ConnectedRepository repo : repositoryRepository.findByConnectionId(connection.getId())) {
            repo.setStatus(RepositoryStatus.DISCONNECTED);
        }
        log.info("User {} revoked GitHub connection", userId);
    }

    /**
     * Lấy kết nối đang hoạt động, tự làm mới token nếu sắp hết hạn (LD-76):
     * <ul>
     *   <li>GitHub từ chối refresh token, hoặc không đọc được token đã lưu: đánh dấu INVALID và
     *       trả 401 GITHUB_REAUTH_REQUIRED để giao diện nhắc người dùng kết nối lại.</li>
     *   <li>Lỗi mạng, GitHub lỗi 5xx: giữ nguyên ACTIVE và ném {@link GitHubApiException} (502), lần sau thử lại.</li>
     *   <li>Nhiều request cùng lúc: chỉ một request làm mới, các request còn lại dùng token mới.</li>
     * </ul>
     */
    public GitHubConnection getActiveConnection(String userId) {
        GitHubConnection connection = connectionRepository.findByUserId(userId)
                .filter(c -> c.getStatus() == ConnectionStatus.ACTIVE)
                .orElseThrow(ApiException::githubNotConnected);
        if (connection.getAccessToken() == null || expiringSoon(connection)) {
            return refreshIfNeeded(userId);
        }
        return connection;
    }

    /** Tìm kết nối của user, bất kể trạng thái. */
    @Transactional(readOnly = true)
    public Optional<GitHubConnection> findConnection(String userId) {
        return connectionRepository.findByUserId(userId);
    }

    /**
     * Gọi khi GitHub trả 401 với token hiện tại. Chỉ đổi trạng thái, không ghi lại cả bản ghi
     * (LD-76: tránh ghi token cũ đè lên token mà request khác vừa làm mới).
     */
    @Transactional
    public void markInvalid(GitHubConnection connection) {
        connectionRepository.updateStatus(connection.getId(), ConnectionStatus.INVALID, Instant.now());
        log.warn("GitHub connection of user {} marked INVALID - re-authorization required",
                connection.getUserId());
    }

    /** Giữ khoá của user trong lúc làm mới; trả về kết nối có token dùng được. */
    private GitHubConnection refreshIfNeeded(String userId) {
        ReentrantLock lock = refreshLocks.computeIfAbsent(userId, key -> new ReentrantLock());
        lock.lock();
        try {
            GitHubConnection refreshed = newTransaction.execute(tx -> refreshInNewTransaction(userId));
            if (refreshed == null) {
                throw ApiException.githubReauthRequired();
            }
            return refreshed;
        } finally {
            lock.unlock();
        }
    }

    /**
     * Chạy trong transaction riêng khi đang giữ khoá: đọc lại kết nối mới nhất rồi mới quyết định
     * có cần làm mới không (request trước có thể vừa làm mới xong). Trả null nếu phải kết nối lại GitHub.
     */
    private GitHubConnection refreshInNewTransaction(String userId) {
        GitHubConnection connection = connectionRepository.findByUserId(userId)
                .filter(c -> c.getStatus() == ConnectionStatus.ACTIVE)
                .orElseThrow(ApiException::githubNotConnected);
        if (connection.getAccessToken() == null) {
            // Không giải mã được token (ví dụ TOKEN_ENCRYPTION_KEY đã đổi): chỉ có thể kết nối lại.
            invalidate(connection);
            return null;
        }
        if (!expiringSoon(connection)) {
            return connection;
        }
        if (connection.getRefreshToken() == null) {
            invalidate(connection);
            return null;
        }
        try {
            applyToken(connection, gitHubClient.refreshToken(connection.getRefreshToken()));
        } catch (GitHubApiException e) {
            if (e.isUnauthorized()) {
                // GitHub trả bad_refresh_token: refresh token hết hạn, đã bị thu hồi hoặc đã dùng rồi.
                invalidate(connection);
                return null;
            }
            log.warn("Could not refresh the GitHub token of user {} (status={}, networkError={}); "
                    + "connection kept ACTIVE", userId, e.getStatusCode(), e.isNetworkError());
            throw e;
        }
        return connectionRepository.save(connection);
    }

    private void invalidate(GitHubConnection connection) {
        connectionRepository.updateStatus(connection.getId(), ConnectionStatus.INVALID, Instant.now());
        log.warn("GitHub connection of user {} marked INVALID - re-authorization required",
                connection.getUserId());
    }

    /**
     * Kết nối lại (LD-76): cùng tài khoản GitHub thì repo bị ngắt khi Disconnect được dùng lại (CONNECTED);
     * tài khoản GitHub khác thì repo cũ chuyển DISCONNECTED cho tới khi đồng bộ lại thành công bằng tài khoản mới.
     */
    private void updateRepositoriesAfterReconnect(GitHubConnection connection, boolean otherAccount) {
        for (ConnectedRepository repo : repositoryRepository.findByConnectionId(connection.getId())) {
            if (otherAccount) {
                repo.setStatus(RepositoryStatus.DISCONNECTED);
            } else if (repo.getStatus() == RepositoryStatus.DISCONNECTED) {
                repo.setStatus(RepositoryStatus.CONNECTED);
            }
        }
        if (otherAccount) {
            log.info("User {} reconnected with another GitHub account: existing repositories marked DISCONNECTED",
                    connection.getUserId());
        }
    }

    /** ACTIVE nhưng không đọc được token (ví dụ TOKEN_ENCRYPTION_KEY đã đổi) thì báo INVALID để người dùng kết nối lại. */
    private static ConnectionStatus effectiveStatus(GitHubConnection connection) {
        return connection.getStatus() == ConnectionStatus.ACTIVE && connection.getAccessToken() == null
                ? ConnectionStatus.INVALID
                : connection.getStatus();
    }

    private static boolean expiringSoon(GitHubConnection connection) {
        Instant expiresAt = connection.getAccessTokenExpiresAt();
        return expiresAt != null && Instant.now().plus(REFRESH_MARGIN).isAfter(expiresAt);
    }

    private void applyToken(GitHubConnection connection, GitHubTokenResponse token) {
        connection.setAccessToken(token.accessToken());
        if (token.refreshToken() != null) {
            connection.setRefreshToken(token.refreshToken());
        }
        connection.setAccessTokenExpiresAt(token.expiresIn() != null
                ? Instant.now().plusSeconds(token.expiresIn())
                : null);
    }
}



