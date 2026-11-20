package com.livingdocs.github.change;

import com.livingdocs.github.entity.SourceChange;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.SourceChangeRepository;
import com.livingdocs.github.service.SourceChangeService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Set;

@Component
public class RevisionJobWorker {
    private static final Logger log = LoggerFactory.getLogger(RevisionJobWorker.class);
    private static final Set<String> RETRYABLE = Set.of("ANALYZER_UNAVAILABLE", "AI_SERVICE_UNAVAILABLE",
            "GITHUB_UNAVAILABLE", "RATE_LIMITED", "GITHUB_INVALID_RESPONSE", "PULL_REQUEST_BASE_CHANGED",
            "UNEXPECTED_FAILURE");

    private final RevisionJobQueue jobs;
    private final ConnectedRepositoryRepository repositories;
    private final SourceChangeRepository changes;
    private final SourceChangeService detector;

    public RevisionJobWorker(RevisionJobQueue jobs, ConnectedRepositoryRepository repositories,
                             SourceChangeRepository changes, SourceChangeService detector) {
        this.jobs = jobs;
        this.repositories = repositories;
        this.changes = changes;
        this.detector = detector;
    }

    @EventListener
    @Transactional(propagation = Propagation.MANDATORY)
    public void enqueue(SourceChangeRequest request) {
        // Keep the delivery, ingestion result, and job in the same transaction.
        if (repositories.lockById(request.repositoryId()).isPresent()) {
            jobs.enqueue(request, now());
        }
    }

    @Scheduled(fixedDelayString = "${revision-jobs.poll-interval-ms:250}")
    public void poll() {
        jobs.claim(now()).ifPresent(this::run);
    }

    private void run(RevisionJobQueue.Lease lease) {
        String errorCode;
        try {
            SourceChangeRequest request = lease.request();
            detector.detect(request);
            errorCode = changes.findByRepositoryIdAndTriggerTypeAndCommitSha(
                            request.repositoryId(), request.trigger(), request.commitSha())
                    .map(RevisionJobWorker::failureCode)
                    .orElse(null);
        } catch (RuntimeException exception) {
            log.warn("Revision job {} failed with {}", lease.id(), exception.getClass().getSimpleName());
            errorCode = "UNEXPECTED_FAILURE";
        }
        jobs.finish(lease, now(), errorCode, errorCode != null && RETRYABLE.contains(errorCode));
    }

    private static String failureCode(SourceChange change) {
        if (change.getStatus() == SourceChange.Status.FAILED) {
            return change.getErrorCode();
        }
        return change.getDocumentsStatus() == SourceChange.DocumentsStatus.FOUND
                ? null : change.getDocumentsErrorCode() == null ? "UNEXPECTED_FAILURE" : change.getDocumentsErrorCode();
    }

    private static OffsetDateTime now() {
        return OffsetDateTime.now(ZoneOffset.UTC);
    }
}
