package com.livingdocs.github.change;

import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.DriftAnalysisService;

import jakarta.annotation.PreDestroy;

/**
 * Checks a pull request for documentation drift as soon as GitHub reports a new head commit, so the report is
 * waiting in Drift Alerts instead of having to be requested by hand. It is opt-in
 * ({@code drift.auto-analysis.enabled=true}) because every pull request then costs GitHub and AI calls.
 *
 * <p>The analysis runs after the webhook has been committed and acknowledged, on a bounded pool: at most
 * {@code max-running} analyses run at once, at most {@code queue-capacity} wait (further ones are dropped and
 * logged), and an analysis that exceeds {@code timeout-seconds} is abandoned. A pull request head that already
 * has a report, or is already queued, is not analysed again. A failure is logged and never reaches the webhook.
 * The report belongs to the user whose GitHub connection the repository was added with.
 */
@Component
@ConditionalOnProperty(name = "drift.auto-analysis.enabled", havingValue = "true")
public class DriftAutoAnalyzer {
    private static final Logger log = LoggerFactory.getLogger(DriftAutoAnalyzer.class);

    private final ConnectedRepositoryRepository repositories;
    private final GitHubConnectionRepository connections;
    private final DriftAnalysisService drift;
    private final long timeoutMillis;
    private final ThreadPoolExecutor queue;
    /** Runs the analysis itself, so that the queue slot can be freed when it takes too long. */
    private final ExecutorService runner = Executors.newCachedThreadPool(DriftAutoAnalyzer::daemon);
    private final Map<String, Boolean> pending = new ConcurrentHashMap<>();

    @Autowired
    public DriftAutoAnalyzer(ConnectedRepositoryRepository repositories, GitHubConnectionRepository connections,
            DriftAnalysisService drift,
            @Value("${drift.auto-analysis.max-running:2}") int maxRunning,
            @Value("${drift.auto-analysis.queue-capacity:20}") int queueCapacity,
            @Value("${drift.auto-analysis.timeout-seconds:120}") long timeoutSeconds) {
        this(repositories, connections, drift, maxRunning, queueCapacity, java.time.Duration.ofSeconds(timeoutSeconds));
    }

    DriftAutoAnalyzer(ConnectedRepositoryRepository repositories, GitHubConnectionRepository connections,
            DriftAnalysisService drift, int maxRunning, int queueCapacity, java.time.Duration timeout) {
        this.repositories = repositories;
        this.connections = connections;
        this.drift = drift;
        this.timeoutMillis = timeout.toMillis();
        this.queue = new ThreadPoolExecutor(maxRunning, maxRunning, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(queueCapacity), DriftAutoAnalyzer::daemon, new ThreadPoolExecutor.AbortPolicy());
    }

    private static Thread daemon(Runnable runnable) {
        Thread thread = new Thread(runnable, "drift-auto-analysis");
        thread.setDaemon(true);
        return thread;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPullRequestHeadChanged(SourceChangeRequest request) {
        if (request.trigger() != SourceChange.Trigger.PULL_REQUEST || request.pullRequestNumber() == null) return;
        String key = request.repositoryId() + "#" + request.pullRequestNumber() + "@" + request.commitSha();
        if (pending.putIfAbsent(key, Boolean.TRUE) != null) {
            log.debug("Automatic drift analysis already queued for {}", key);
            return;
        }
        try {
            queue.execute(() -> {
                try {
                    analyze(request);
                } finally {
                    pending.remove(key);
                }
            });
        } catch (RejectedExecutionException full) {
            pending.remove(key);
            log.warn("Automatic drift analysis queue is full; skipped pull request #{} of {}",
                    request.pullRequestNumber(), request.repositoryId());
        }
    }

    /** Runs one analysis within the time limit. Never throws. */
    void analyze(SourceChangeRequest request) {
        CompletableFuture<Void> work = CompletableFuture.runAsync(() -> doAnalyze(request), runner);
        try {
            work.get(timeoutMillis, TimeUnit.MILLISECONDS);
        } catch (TimeoutException late) {
            work.cancel(true);
            log.warn("Automatic drift analysis of pull request #{} in {} timed out after {} ms",
                    request.pullRequestNumber(), request.repositoryId(), timeoutMillis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (ExecutionException failure) {
            log.warn("Automatic drift analysis of pull request #{} in {} failed: {}", request.pullRequestNumber(),
                    request.repositoryId(), failure.getCause() == null ? failure.getMessage() : failure.getCause().getMessage());
        }
    }

    private void doAnalyze(SourceChangeRequest request) {
        var repository = repositories.findById(request.repositoryId()).orElse(null);
        if (repository == null || repository.getConnectionId() == null) return;
        var connection = connections.findById(repository.getConnectionId()).orElse(null);
        if (connection == null) return;
        String owner = connection.getUserId();
        if (alreadyAnalysed(owner, request)) {
            log.debug("Pull request #{} of {} was already analysed at this head", request.pullRequestNumber(),
                    request.repositoryId());
            return;
        }
        drift.analyzePullRequest(owner, request.repositoryId(),
                new DriftAnalysisRequest(request.pullRequestNumber(), null, true));
    }

    /** True when a stored report of this pull request was made for exactly this head commit. */
    private boolean alreadyAnalysed(String owner, SourceChangeRequest request) {
        if (request.commitSha() == null) return false;
        JsonNode reports = drift.listReports(owner, request.repositoryId(), request.pullRequestNumber());
        if (reports == null || !reports.isArray()) return false;
        for (JsonNode report : reports) {
            if (request.commitSha().equalsIgnoreCase(report.path("head_sha").asText(""))) return true;
        }
        return false;
    }

    @PreDestroy
    void stop() {
        queue.shutdownNow();
        runner.shutdownNow();
    }
}
