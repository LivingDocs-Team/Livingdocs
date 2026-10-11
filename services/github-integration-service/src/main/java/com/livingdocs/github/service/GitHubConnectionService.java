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
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.util.UriComponentsBuilder;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

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

    public GitHubConnectionService(GitHubProperties props,
                                   GitHubClient gitHubClient,
                                   OAuthStateStore stateStore,
                                   GitHubConnectionRepository connectionRepository,
                                   ConnectedRepositoryRepository repositoryRepository) {
        this.props = props;
        this.gitHubClient = gitHubClient;
        this.stateStore = stateStore;
        this.connectionRepository = connectionRepository;
        this.repositoryRepository = repositoryRepository;
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
        connection.setUserId(userId);
        connection.setGithubUserId(user.id());
        connection.setGithubLogin(user.login());
        applyToken(connection, token);
        connection.setStatus(ConnectionStatus.ACTIVE);
        GitHubConnection saved = connectionRepository.save(connection);
        log.info("User {} connected GitHub account {}", userId, user.login());
        return saved;
    }

    @Transactional(readOnly = true)
    public ConnectionResponse getStatus(String userId) {
        return connectionRepository.findByUserId(userId)
                .map(c -> new ConnectionResponse(
                        c.getStatus() == ConnectionStatus.ACTIVE,
                        c.getGithubLogin(),
                        c.getStatus().name(),
                        c.getCreatedAt(),
                        c.getAccessTokenExpiresAt()))
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
     * Lấy kết nối đang hoạt động, tự làm mới token nếu sắp hết hạn.
     * Nếu token hỏng thì đánh dấu INVALID để giao diện nhắc người dùng kết nối lại.
     */
    @Transactional(noRollbackFor = ApiException.class)
    public GitHubConnection getActiveConnection(String userId) {
        GitHubConnection connection = connectionRepository.findByUserId(userId)
                .filter(c -> c.getStatus() == ConnectionStatus.ACTIVE)
                .orElseThrow(ApiException::githubNotConnected);

        Instant expiresAt = connection.getAccessTokenExpiresAt();
        boolean expiringSoon = expiresAt != null && Instant.now().plus(REFRESH_MARGIN).isAfter(expiresAt);
        if (expiringSoon) {
            if (connection.getRefreshToken() == null) {
                markInvalid(connection);
                throw ApiException.githubReauthRequired();
            }
            try {
                applyToken(connection, gitHubClient.refreshToken(connection.getRefreshToken()));
                connectionRepository.save(connection);
            } catch (GitHubApiException e) {
                markInvalid(connection);
                throw ApiException.githubReauthRequired();
            }
        }
        return connection;
    }

    /** Tìm kết nối của user, bất kể trạng thái. */
    @Transactional(readOnly = true)
    public Optional<GitHubConnection> findConnection(String userId) {
        return connectionRepository.findByUserId(userId);
    }

    /** Gọi khi GitHub trả 401 với token hiện tại. */
    @Transactional
    public void markInvalid(GitHubConnection connection) {
        connection.setStatus(ConnectionStatus.INVALID);
        connectionRepository.save(connection);
        log.warn("GitHub connection of user {} marked INVALID - re-authorization required",
                connection.getUserId());
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
