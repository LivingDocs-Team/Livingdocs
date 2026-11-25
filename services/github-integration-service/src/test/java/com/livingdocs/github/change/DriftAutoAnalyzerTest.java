package com.livingdocs.github.change;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.dto.DriftAnalysisRequest;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.DriftAnalysisService;

class DriftAutoAnalyzerTest {
    private static final String SHA = "a".repeat(40);

    private final ConnectedRepositoryRepository repositories = mock(ConnectedRepositoryRepository.class);
    private final GitHubConnectionRepository connections = mock(GitHubConnectionRepository.class);
    private final DriftAnalysisService drift = mock(DriftAnalysisService.class);
    private final UUID repositoryId = UUID.randomUUID();
    private final UUID connectionId = UUID.randomUUID();
    private DriftAutoAnalyzer analyzer;

    private DriftAutoAnalyzer analyzer(int running, int queue, long timeoutMillis) {
        ConnectedRepository repository = new ConnectedRepository();
        repository.setConnectionId(connectionId);
        when(repositories.findById(repositoryId)).thenReturn(Optional.of(repository));
        GitHubConnection connection = new GitHubConnection();
        connection.setUserId("owner-1");
        when(connections.findById(connectionId)).thenReturn(Optional.of(connection));
        when(drift.listReports(any(), any(), any())).thenReturn(new ObjectMapper().createArrayNode());
        analyzer = new DriftAutoAnalyzer(repositories, connections, drift, running, queue,
                java.time.Duration.ofMillis(timeoutMillis));
        return analyzer;
    }

    @AfterEach
    void stop() {
        if (analyzer != null) analyzer.stop();
    }

    private SourceChangeRequest request(int pullRequest, String sha) {
        return new SourceChangeRequest(repositoryId, SourceChange.Trigger.PULL_REQUEST, sha, pullRequest);
    }

    @Test
    void aPullRequestHeadChangeIsAnalysedForTheUserWhoConnectedTheRepository() {
        analyzer(1, 5, 5_000).onPullRequestHeadChanged(request(7, SHA));
        verify(drift, timeout(2_000)).analyzePullRequest(eq("owner-1"), eq(repositoryId), any(DriftAnalysisRequest.class));
    }

    @Test
    void aCommitIsNeverAnalysed() {
        analyzer(1, 5, 5_000).onPullRequestHeadChanged(
                new SourceChangeRequest(repositoryId, SourceChange.Trigger.COMMIT, SHA, null));
        verify(drift, never()).analyzePullRequest(any(), any(), any());
    }

    @Test
    void aHeadThatAlreadyHasAReportIsNotAnalysedAgain() throws Exception {
        analyzer(1, 5, 5_000);
        JsonNode reports = new ObjectMapper().readTree("[{\"id\":\"r1\",\"head_sha\":\"" + SHA + "\"}]");
        when(drift.listReports("owner-1", repositoryId, 7)).thenReturn(reports);
        analyzer.analyze(request(7, SHA));
        verify(drift, never()).analyzePullRequest(any(), any(), any());
        // a different head of the same pull request is analysed
        analyzer.analyze(request(7, "b".repeat(40)));
        verify(drift).analyzePullRequest(eq("owner-1"), eq(repositoryId), any(DriftAnalysisRequest.class));
    }

    @Test
    void aDuplicateDeliveryWhileTheSameHeadIsQueuedIsIgnored() throws Exception {
        analyzer(1, 5, 5_000);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch started = new CountDownLatch(1);
        when(drift.analyzePullRequest(any(), any(), any())).thenAnswer(call -> {
            started.countDown();
            release.await(5, TimeUnit.SECONDS);
            return null;
        });
        analyzer.onPullRequestHeadChanged(request(7, SHA));
        assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();
        analyzer.onPullRequestHeadChanged(request(7, SHA));
        analyzer.onPullRequestHeadChanged(request(7, SHA));
        release.countDown();
        verify(drift, timeout(2_000).times(1)).analyzePullRequest(any(), any(), any());
        verify(drift, times(1)).analyzePullRequest(any(), any(), any());
    }

    @Test
    void whenTheQueueIsFullFurtherPullRequestsAreDroppedWithoutFailingTheWebhook() throws Exception {
        analyzer(1, 1, 10_000);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch started = new CountDownLatch(1);
        when(drift.analyzePullRequest(any(), any(), any())).thenAnswer(call -> {
            started.countDown();
            release.await(5, TimeUnit.SECONDS);
            return null;
        });
        analyzer.onPullRequestHeadChanged(request(1, SHA));       // running
        assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();
        analyzer.onPullRequestHeadChanged(request(2, SHA));       // queued
        assertThatCode(() -> analyzer.onPullRequestHeadChanged(request(3, SHA)))   // dropped
                .doesNotThrowAnyException();
        release.countDown();
        verify(drift, timeout(3_000).times(2)).analyzePullRequest(any(), any(), any());
    }

    @Test
    void anAnalysisThatTakesTooLongIsAbandonedAndTheNextOneStillRuns() throws Exception {
        analyzer(1, 5, 150);
        CountDownLatch never = new CountDownLatch(1);
        when(drift.analyzePullRequest(eq("owner-1"), eq(repositoryId), any())).thenAnswer(call -> {
            DriftAnalysisRequest asked = call.getArgument(2);
            if (asked.pullRequestNumber() == 1) never.await(5, TimeUnit.SECONDS);
            return null;
        });
        analyzer.onPullRequestHeadChanged(request(1, SHA));
        analyzer.onPullRequestHeadChanged(request(2, SHA));
        verify(drift, timeout(3_000).times(2)).analyzePullRequest(any(), any(), any());
        never.countDown();
    }

    @Test
    void aFailingAnalysisIsSwallowed() {
        analyzer(1, 5, 5_000);
        when(drift.analyzePullRequest(any(), any(), any())).thenThrow(new IllegalStateException("GitHub is down"));
        assertThatCode(() -> analyzer.analyze(request(7, SHA))).doesNotThrowAnyException();
    }

    @Test
    void aMissingRepositoryOrConnectionIsIgnored() {
        analyzer(1, 5, 5_000);
        when(repositories.findById(repositoryId)).thenReturn(Optional.empty());
        analyzer.analyze(request(7, SHA));
        verify(drift, never()).analyzePullRequest(any(), any(), any());
    }
}
