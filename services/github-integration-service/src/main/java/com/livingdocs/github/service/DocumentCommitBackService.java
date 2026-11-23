package com.livingdocs.github.service;

import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.client.GitHubTree;
import com.livingdocs.github.entity.DocumentWorkflowAudit;
import com.livingdocs.github.entity.DocumentWorkflowStatus;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentWorkflowAuditRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Service
public class DocumentCommitBackService {
    private static final String DIRECTORY = ".livingdocs";
    private static final String AUDIT_ACTION = "COMMIT_BACK_CONFIRMED";
    private final DocumentWorkflowRepository workflows;
    private final ConnectedRepositoryRepository repositories;
    private final DocumentationGenerationService documents;
    private final GitHubConnectionService connections;
    private final GitHubClient github;
    private final DocumentWorkflowAuditRepository audit;
    // Optional so that unit tests can build the service without it; without it the defaults apply.
    private ApprovalPolicyService policies;

    @org.springframework.beans.factory.annotation.Autowired(required = false)
    void setPolicies(ApprovalPolicyService policies) {
        this.policies = policies;
    }

    public DocumentCommitBackService(DocumentWorkflowRepository workflows, ConnectedRepositoryRepository repositories,
            DocumentationGenerationService documents, GitHubConnectionService connections, GitHubClient github,
            DocumentWorkflowAuditRepository audit) {
        this.workflows = workflows;
        this.repositories = repositories;
        this.documents = documents;
        this.connections = connections;
        this.github = github;
        this.audit = audit;
    }

    @Transactional
    public Result commit(String actor, Set<String> authorities, UUID workflowId, int version) {
        if (!authorities.containsAll(Set.of("ROLE_MANAGER", "DOCUMENT_APPROVE"))) {
            throw ApiException.forbidden("Manager approval permission is required.");
        }
        ApprovalPolicyService.MergeSettings merge = policies == null ? null : policies.merge();
        if (merge != null && !merge.allowCommitBack()) {
            throw conflict("The merge policy does not allow publishing approved documents to GitHub.");
        }
        var workflow = workflows.lockById(workflowId).orElseThrow(() -> ApiException.notFound("Workflow not found."));
        if (!actor.equals(workflow.getManagerUserId())) {
            throw ApiException.notFound("Workflow not found.");
        }
        if (workflow.getStatus() != DocumentWorkflowStatus.APPROVED
                || !Objects.equals(workflow.getSubmittedDocumentVersion(), version)) {
            throw conflict("The requested document version is not approved.");
        }
        String documentId = workflow.getDocumentId();
        if (!documentId.matches("[0-9a-f]{32}")) {
            throw conflict("The document does not have a supported publication path.");
        }
        var document = documents.getDocument(actor, documentId);
        if (!workflow.getOwnerUserId().equals(document.path("owner_user_id").asText())
                || document.path("current_version").asInt() != version) {
            throw conflict("The approved version is no longer current.");
        }
        var publication = documents.getExactDocumentVersion(actor, documentId, version);
        var source = publication.path("source_snapshot");
        String sha = source.path("commit_sha").asText();
        String branch = source.path("branch").asText();
        if (!"accepted".equals(publication.path("status").asText())
                || !"source_change".equals(publication.path("origin").asText())
                || !source.path("pull_request_number").isNull()
                || !sha.matches("[0-9a-f]{40}") || branch.isBlank()
                || !publication.path("content").isTextual()) {
            throw conflict("Commit-back requires an approved revision from a default-branch push.");
        }
        UUID repositoryId;
        try {
            repositoryId = UUID.fromString(source.path("repository_id").asText());
        } catch (IllegalArgumentException invalidRepository) {
            throw conflict("The approved revision has no valid repository identity.");
        }
        var repo = repositories.lockById(repositoryId).orElseThrow(() -> conflict("The repository is disconnected."));
        if (repo.getStatus() == RepositoryStatus.DISCONNECTED
                || !repo.getFullName().equalsIgnoreCase(source.path("repository_full_name").asText())
                || !branch.equals(repo.getDefaultBranch())) {
            throw conflict("The source no longer matches the connected repository and default branch.");
        }
        String token = connections.getActiveConnection(actor).getAccessToken();
        if (token == null || token.isBlank()) {
            throw ApiException.githubNotConnected();
        }

        String path = DIRECTORY + "/" + documentId + "-v" + version + ".md";
        byte[] content = publication.path("content").textValue().getBytes(StandardCharsets.UTF_8);
        try {
            String[] name = repo.getFullName().split("/", 2);
            var remote = github.getPublicationBranch(token, name[0], name[1]);
            if (!Objects.equals(repo.getGithubRepoId(), remote.repositoryId())
                    || !branch.equals(remote.branch()) || !repo.getFullName().equalsIgnoreCase(remote.repositoryName())
                    || remote.refId().isBlank() || !remote.headSha().matches("[0-9a-f]{40}")
                    || !remote.treeSha().matches("[0-9a-f]{40}")) {
                throw conflict("The GitHub repository and default branch head could not be verified.");
            }
            GitHubTree tree = github.getTree(token, name[0], name[1], remote.treeSha());
            if (tree == null || tree.truncated() || tree.tree() == null || !remote.treeSha().equals(tree.sha())) {
                throw conflict("The GitHub tree could not be checked for an existing file.");
            }
            for (var entry : tree.tree()) {
                if (DIRECTORY.equalsIgnoreCase(entry.path())
                        && (!DIRECTORY.equals(entry.path()) || !"tree".equals(entry.type()))) {
                    throw conflict("The publication directory is occupied.");
                }
                if (path.equalsIgnoreCase(entry.path())) {
                    if (!sha.equals(remote.headSha()) && path.equals(entry.path())
                            && "100644".equals(entry.mode()) && blobSha(content).equals(entry.sha())) {
                        return confirmPublication(workflowId, version, actor, sha,
                                new Result(path, remote.headSha(), true));
                    }
                    throw conflict("A file already occupies the publication path.");
                }
            }
            if (!sha.equals(remote.headSha())) {
                throw conflict("The source branch advanced. Review a new revision before committing.");
            }
            String committed = github.commitFileOnBranch(token, remote.refId(), sha, path, content,
                    merge == null ? "Publish LivingDocs document " + documentId + " v" + version
                            : merge.message(documentId, version));
            return confirmPublication(workflowId, version, actor, sha, new Result(path, committed, false));
        } catch (GitHubApiException e) {
            if (e.isUnauthorized() || e.isNotFound() || e.getStatusCode() == 403 && !e.isRateLimited()) {
                throw ApiException.forbidden("GitHub denied access to the repository.");
            }
            throw new ApiException(HttpStatus.BAD_GATEWAY, "GITHUB_COMMIT_UNCONFIRMED",
                    "GitHub did not confirm the commit. Retry to check the published path.");
        }
    }

    private Result confirmPublication(UUID workflowId, int version, String actor, String sourceSha, Result result) {
        // commit() holds the workflow row lock across confirmation and persistence.
        if (!audit.existsByWorkflowIdAndDocumentVersionAndAction(workflowId, version, AUDIT_ACTION)) {
            String reason = result.alreadyPresent() ? "Verified existing publication" : "Published approved version";
            var entry = new DocumentWorkflowAudit(workflowId, actor, AUDIT_ACTION, "APPROVED", "APPROVED",
                    reason + " at " + result.path() + "; source " + sourceSha
                            + "; observed head " + result.observedHeadSha(), null, null, "MANAGER");
            entry.setDocumentVersion(version);
            entry.setTriggerSource("COMMIT_BACK");
            audit.save(entry);
        }
        return result;
    }

    private static String blobSha(byte[] content) {
        try {
            var hash = MessageDigest.getInstance("SHA-1");
            // Git object identity, independent of the HTTP payload encoding.
            hash.update(("blob " + content.length + "\0").getBytes(StandardCharsets.US_ASCII));
            return HexFormat.of().formatHex(hash.digest(content));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("Git blob digest unavailable", e);
        }
    }

    private static ApiException conflict(String message) {
        return new ApiException(HttpStatus.CONFLICT, "DOCUMENT_COMMIT_CONFLICT", message);
    }

    public record Result(String path, String observedHeadSha, boolean alreadyPresent) {
    }
}
