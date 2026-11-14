package com.livingdocs.github.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.change.SourceChangeRequest;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubPullRequest;
import com.livingdocs.github.dto.CommitResponse;
import com.livingdocs.github.dto.PullRequestResponse;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.IngestionSource;
import com.livingdocs.github.entity.RepositoryCommit;
import com.livingdocs.github.entity.RepositoryPullRequest;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.entity.WebhookDelivery;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.RepositoryCommitRepository;
import com.livingdocs.github.repository.RepositoryPullRequestRepository;
import com.livingdocs.github.repository.WebhookDeliveryRepository;
import com.livingdocs.github.sync.RepositorySnapshot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.UUID;

/**
 * LD-68 - nhận Pull Request và commit của các repository đã kết nối:
 * từ webhook GitHub (push, pull_request) và lấy bù sau mỗi lần đồng bộ (khi webhook bị lỡ).
 * Mọi bước ghi đều idempotent: cùng commit (SHA) hay cùng PR (số) chỉ có một dòng cho mỗi repo.
 */
@Service
public class IngestionService {

    public enum Result { PROCESSED, DUPLICATE, IGNORED }

    static final int BACKFILL_PULL_REQUESTS = 30;
    static final int LIST_LIMIT = 100;

    private static final Logger log = LoggerFactory.getLogger(IngestionService.class);
    private static final String BRANCH_PREFIX = "refs/heads/";

    private final ConnectedRepositoryRepository repositoryRepository;
    private final RepositoryCommitRepository commitRepository;
    private final RepositoryPullRequestRepository pullRequestRepository;
    private final WebhookDeliveryRepository deliveryRepository;
    private final GitHubClient gitHubClient;
    private final ObjectMapper objectMapper;
    private final TransactionTemplate transaction;
    private final ApplicationEventPublisher events;

    public IngestionService(ConnectedRepositoryRepository repositoryRepository,
                            RepositoryCommitRepository commitRepository,
                            RepositoryPullRequestRepository pullRequestRepository,
                            WebhookDeliveryRepository deliveryRepository,
                            GitHubClient gitHubClient,
                            ObjectMapper objectMapper,
                            PlatformTransactionManager transactionManager,
                            ApplicationEventPublisher events) {
        this.repositoryRepository = repositoryRepository;
        this.commitRepository = commitRepository;
        this.pullRequestRepository = pullRequestRepository;
        this.deliveryRepository = deliveryRepository;
        this.gitHubClient = gitHubClient;
        this.objectMapper = objectMapper;
        this.transaction = new TransactionTemplate(transactionManager);
        this.events = events;
    }

    // ------------------------------------------------------------------ Webhook (LD-69, LD-70)

    /**
     * Xử lý một webhook đã kiểm chữ ký. Chỉ nhận push và pull_request của repo đã có trong workspace (BR-25).
     * Ghi delivery và dữ liệu trong cùng transaction: lỗi giữa chừng thì không ghi gì, GitHub gửi lại vẫn xử lý được.
     */
    @Transactional
    public Result handleWebhook(String deliveryId, String event, JsonNode payload) {
        if (!"push".equals(event) && !"pull_request".equals(event)) {
            return Result.IGNORED;
        }
        long githubRepoId = payload.path("repository").path("id").asLong(0);
        List<ConnectedRepository> repos = repositoryRepository.findByGithubRepoId(githubRepoId);
        if (repos.isEmpty()) {
            return Result.IGNORED;
        }
        if (deliveryRepository.existsById(deliveryId)) {
            return Result.DUPLICATE;
        }
        deliveryRepository.save(new WebhookDelivery(deliveryId, event, githubRepoId));

        for (ConnectedRepository repo : repos) {
            if ("push".equals(event)) {
                savePush(repo, payload);
            } else {
                GitHubPullRequest pr = toPullRequest(payload.path("pull_request"));
                boolean newHead = savePullRequest(repo.getId(), pr, IngestionSource.WEBHOOK);
                // LD-119: Pull Request đang mở có commit head mới (opened, synchronize) thì phát hiện thay đổi
                if (newHead && "open".equals(pr.state())) {
                    events.publishEvent(new SourceChangeRequest(repo.getId(), SourceChange.Trigger.PULL_REQUEST,
                            pr.head().sha(), pr.number()));
                }
            }
        }
        return Result.PROCESSED;
    }

    private void savePush(ConnectedRepository repo, JsonNode payload) {
        String ref = payload.path("ref").asText("");
        // Xoá nhánh hoặc push tag: không có commit mới của nhánh nào
        if (payload.path("deleted").asBoolean(false) || !ref.startsWith(BRANCH_PREFIX)) {
            return;
        }
        String branch = ref.substring(BRANCH_PREFIX.length());
        // LD-118: tài liệu đi theo nhánh mặc định, nên chỉ commit mới trên nhánh này mới phát hiện thay đổi
        // (thay đổi trên nhánh khác được xét qua Pull Request)
        boolean detectChanges = repo.getDefaultBranch() == null || repo.getDefaultBranch().equals(branch);
        for (JsonNode commit : payload.path("commits")) {
            JsonNode author = commit.path("author");
            String sha = text(commit, "id");
            boolean inserted = saveCommit(repo.getId(), sha, branch, text(commit, "message"),
                    text(author, "name"), text(author, "username"), parseTime(text(commit, "timestamp")),
                    text(commit, "url"), IngestionSource.WEBHOOK);
            if (inserted && detectChanges) {
                events.publishEvent(new SourceChangeRequest(repo.getId(), SourceChange.Trigger.COMMIT, sha, null));
            }
        }
    }

    private GitHubPullRequest toPullRequest(JsonNode node) {
        try {
            return objectMapper.treeToValue(node, GitHubPullRequest.class);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Invalid pull_request payload", e);
        }
    }

    // ------------------------------------------------------------------ Lấy bù khi đồng bộ

    /**
     * Sau một lần đồng bộ thành công: lưu các commit gần nhất đã có trong snapshot và các PR cập nhật gần nhất.
     * Không lấy được danh sách PR thì chỉ ghi log, không làm hỏng lần đồng bộ.
     */
    public void backfill(ConnectedRepository repo, RepositorySnapshot snapshot, String accessToken) {
        List<GitHubPullRequest> pullRequests = List.of();
        String[] parts = repo.getFullName().split("/", 2);
        try {
            pullRequests = gitHubClient.listPullRequests(accessToken, parts[0], parts[1], BACKFILL_PULL_REQUESTS);
        } catch (GitHubApiException e) {
            log.warn("Could not list pull requests of {} after sync: {}", repo.getFullName(), e.getMessage());
        }

        List<GitHubPullRequest> prs = pullRequests;
        transaction.executeWithoutResult(status -> {
            for (RepositorySnapshot.CommitInfo c : snapshot.recentCommits()) {
                saveCommit(repo.getId(), c.sha(), snapshot.branch(), c.message(), c.authorName(),
                        c.authorLogin(), c.committedAt(), c.htmlUrl(), IngestionSource.SYNC);
            }
            for (GitHubPullRequest pr : prs) {
                savePullRequest(repo.getId(), pr, IngestionSource.SYNC);
            }
        });
    }

    // ------------------------------------------------------------------ Xem (màn hình PR & Commit List)

    @Transactional(readOnly = true)
    public List<CommitResponse> listCommits(UUID repositoryId) {
        return commitRepository.findByRepositoryIdOrderByCommittedAtDesc(repositoryId, PageRequest.of(0, LIST_LIMIT))
                .stream().map(CommitResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public List<PullRequestResponse> listPullRequests(UUID repositoryId) {
        return pullRequestRepository.findByRepositoryIdOrderByUpdatedAtDesc(repositoryId, PageRequest.of(0, LIST_LIMIT))
                .stream().map(PullRequestResponse::from).toList();
    }

    // ------------------------------------------------------------------ Lưu (LD-71, LD-72)

    /** true nếu commit vừa được lưu lần đầu. */
    private boolean saveCommit(UUID repositoryId, String sha, String branch, String message, String authorName,
                               String authorLogin, Instant committedAt, String htmlUrl, IngestionSource source) {
        RepositoryCommit existing = commitRepository.findByRepositoryIdAndSha(repositoryId, sha).orElse(null);
        if (existing != null) {
            return false; // commit không đổi theo thời gian; nhánh giữ theo lần nhận đầu tiên
        }
        RepositoryCommit commit = new RepositoryCommit();
        commit.setRepositoryId(repositoryId);
        commit.setSha(sha);
        commit.setBranch(branch);
        commit.setMessage(message);
        commit.setAuthorName(authorName);
        commit.setAuthorLogin(authorLogin);
        commit.setCommittedAt(committedAt);
        commit.setHtmlUrl(htmlUrl);
        commit.setSource(source);
        commitRepository.save(commit);
        return true;
    }

    /** true nếu Pull Request có commit head khác lần lưu trước (hoặc vừa được lưu lần đầu). */
    private boolean savePullRequest(UUID repositoryId, GitHubPullRequest pr, IngestionSource source) {
        RepositoryPullRequest row = pullRequestRepository.findByRepositoryIdAndNumber(repositoryId, pr.number())
                .orElse(null);
        String previousHead = null;
        if (row == null) {
            row = new RepositoryPullRequest();
            row.setRepositoryId(repositoryId);
            row.setNumber(pr.number());
            row.setSource(source);
        } else if (row.getUpdatedAt() != null && pr.updatedAt() != null && pr.updatedAt().isBefore(row.getUpdatedAt())) {
            return false; // event cũ đến sau event mới: giữ dữ liệu mới hơn
        } else {
            previousHead = row.getHeadSha();
        }
        row.setTitle(pr.title());
        row.setState(pr.state());
        row.setAuthorLogin(pr.user() == null ? null : pr.user().login());
        row.setHeadRef(pr.head() == null ? null : pr.head().ref());
        row.setHeadSha(pr.head() == null ? null : pr.head().sha());
        row.setBaseRef(pr.base() == null ? null : pr.base().ref());
        row.setHtmlUrl(pr.htmlUrl());
        row.setCreatedAt(pr.createdAt());
        row.setUpdatedAt(pr.updatedAt());
        row.setClosedAt(pr.closedAt());
        row.setMergedAt(pr.mergedAt());
        pullRequestRepository.save(row);
        return row.getHeadSha() != null && !row.getHeadSha().equals(previousHead);
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isTextual() ? value.asText() : null;
    }

    /** Thời điểm commit trong webhook push có múi giờ, ví dụ 2026-11-06T10:15:00+07:00. */
    private static Instant parseTime(String value) {
        if (value == null) {
            return null;
        }
        try {
            return OffsetDateTime.parse(value).toInstant();
        } catch (DateTimeParseException e) {
            return null;
        }
    }
}



