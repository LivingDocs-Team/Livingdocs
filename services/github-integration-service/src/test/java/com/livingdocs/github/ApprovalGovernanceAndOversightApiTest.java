package com.livingdocs.github;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livingdocs.github.client.GitHubClient;
import com.livingdocs.github.entity.ConnectedRepository;
import com.livingdocs.github.entity.ConnectionStatus;
import com.livingdocs.github.entity.DocumentWorkflow;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.entity.RepositoryStatus;
import com.livingdocs.github.repository.ConnectedRepositoryRepository;
import com.livingdocs.github.repository.DocumentWorkflowRepository;
import com.livingdocs.github.repository.GitHubConnectionRepository;
import com.livingdocs.github.service.RepositorySyncService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Approval and merge policies, Manager delegations and the read-only oversight views. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(com.livingdocs.github.security.InternalServiceTestMvcConfig.class)
class ApprovalGovernanceAndOversightApiTest {
    private static final String MANAGER = "ROLE_MANAGER,DOCUMENT_APPROVAL_QUEUE_VIEW,DOCUMENT_APPROVE";
    private static final String DEVELOPER = "ROLE_DEVELOPER,DOCUMENT_VIEW,DOCUMENT_CREATE";
    private static final String TECHNICAL_LEAD = "ROLE_TECHNICAL_LEAD,DOCUMENT_TECHNICAL_REVIEW";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;
    @Autowired JdbcTemplate jdbc;
    @Autowired GitHubConnectionRepository connections;
    @Autowired ConnectedRepositoryRepository repositories;
    @Autowired DocumentWorkflowRepository workflows;

    @MockitoBean GitHubClient gitHubClient;
    @MockitoBean RepositorySyncService repositorySyncService;

    private UUID repositoryId;
    private UUID workflowId;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM approval_delegations");
        jdbc.update("DELETE FROM approval_policies");
        jdbc.update("DELETE FROM auto_update_policies");
        workflows.deleteAll();
        repositories.deleteAll();
        connections.deleteAll();

        GitHubConnection connection = new GitHubConnection();
        connection.setUserId("owner-1");
        connection.setGithubUserId(1L);
        connection.setGithubLogin("owner");
        connection.setStatus(ConnectionStatus.ACTIVE);
        connection = connections.save(connection);
        ConnectedRepository repository = new ConnectedRepository();
        repository.setWorkspaceId("ws-owner-1");
        repository.setConnectionId(connection.getId());
        repository.setGithubRepoId(9L);
        repository.setFullName("acme/shop");
        repository.setDefaultBranch("main");
        repository.setHtmlUrl("https://github.com/acme/shop");
        repository.setStatus(RepositoryStatus.CONNECTED);
        repositoryId = repositories.save(repository).getId();

        DocumentWorkflow workflow = new DocumentWorkflow("doc-1", "Shop guide", "owner-1");
        workflow.submit(1);
        workflowId = workflows.saveAndFlush(workflow).getId();
    }

    // ---------- policies ----------

    @Test
    void policiesStartWithTheDefaultsAndAManagerCanChangeThem() throws Exception {
        mvc.perform(get("/api/approval/policies/approval").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.settings.requireManagerComment").value(false))
                .andExpect(jsonPath("$.updatedBy").doesNotExist());

        mvc.perform(put("/api/approval/policies/approval").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"requireStaffComment\":true,\"requireManagerComment\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.settings.requireStaffComment").value(true))
                .andExpect(jsonPath("$.updatedBy").value("m1"));

        mvc.perform(get("/api/approval/policies/approval").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(jsonPath("$.settings.requireManagerComment").value(true));
    }

    @Test
    void mergePolicyValidatesTheCommitMessageTemplate() throws Exception {
        mvc.perform(put("/api/approval/policies/merge").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"allowCommitBack\":true,\"commitMessageTemplate\":\"docs: {document} v{version}\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.settings.commitMessageTemplate").value("docs: {document} v{version}"));
        mvc.perform(put("/api/approval/policies/merge").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"allowCommitBack\":true,\"commitMessageTemplate\":\"docs {author}\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(put("/api/approval/policies/merge").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"allowCommitBack\":\"yes\",\"commitMessageTemplate\":\"docs\"}"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/approval/policies/other").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(status().isNotFound());
    }

    @Test
    void policiesAreForManagersOnly() throws Exception {
        mvc.perform(get("/api/approval/policies/approval").header("X-User-Id", "d1").header("X-User-Authorities", DEVELOPER))
                .andExpect(status().isForbidden());
        mvc.perform(put("/api/approval/policies/approval").header("X-User-Id", "d1").header("X-User-Authorities", DEVELOPER)
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void theApprovalPolicyCanRequireAManagerCommentOnApproval() throws Exception {
        mvc.perform(put("/api/approval/policies/approval").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"requireManagerComment\":true}"))
                .andExpect(status().isOk());
        DocumentWorkflow workflow = workflows.findById(workflowId).orElseThrow();
        workflow.claim("staff-1");
        workflow.review(com.livingdocs.github.entity.StaffReviewResult.PASSED, "Checked");
        workflows.saveAndFlush(workflow);

        mvc.perform(post("/api/document-workflows/{id}/approve", workflowId).header("X-User-Id", "m1")
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("The approval policy requires a comment with every approval."));
    }

    @Test
    void theMergePolicyCanSwitchPublishingToGitHubOff() throws Exception {
        mvc.perform(put("/api/approval/policies/merge").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"allowCommitBack\":false,\"commitMessageTemplate\":\"docs: {document}\"}"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/document-workflows/{id}/versions/1/github-commit", workflowId).header("X-User-Id", "m1")
                        .header("X-User-Authorities", MANAGER))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message").value("The merge policy does not allow publishing approved documents to GitHub."));
    }

    // ---------- delegations ----------

    @Test
    void aManagerDelegatesAndRevokesAndTheDelegateSeesIt() throws Exception {
        String ends = Instant.now().plusSeconds(3 * 86400).toString();
        String created = mvc.perform(post("/api/approval/delegations").header("X-User-Id", "m1")
                        .header("X-User-Authorities", MANAGER).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"delegateUserId\":\"m2\",\"reason\":\"On leave\",\"endsAt\":\"" + ends + "\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.state").value("ACTIVE"))
                .andReturn().getResponse().getContentAsString();
        String id = objectMapper.readTree(created).get("id").asText();

        mvc.perform(get("/api/approval/delegations").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(jsonPath("$.outgoing.length()").value(1))
                .andExpect(jsonPath("$.incoming.length()").value(0));
        mvc.perform(get("/api/approval/delegations").header("X-User-Id", "m2").header("X-User-Authorities", MANAGER))
                .andExpect(jsonPath("$.incoming[0].delegatorUserId").value("m1"));

        mvc.perform(delete("/api/approval/delegations/{id}", id).header("X-User-Id", "m2").header("X-User-Authorities", MANAGER))
                .andExpect(status().isNotFound());               // only the delegator revokes
        mvc.perform(delete("/api/approval/delegations/{id}", id).header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(status().isNoContent());
        mvc.perform(get("/api/approval/delegations").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER))
                .andExpect(jsonPath("$.outgoing[0].state").value("REVOKED"));
    }

    @Test
    void delegationRejectsSelfPastEndAndTooLongPeriods() throws Exception {
        String future = Instant.now().plusSeconds(86400).toString();
        String tooLong = Instant.now().plusSeconds(200L * 86400).toString();
        String past = Instant.now().minusSeconds(60).toString();
        for (String body : new String[] {
                "{\"delegateUserId\":\"m1\",\"endsAt\":\"" + future + "\"}",
                "{\"delegateUserId\":\"m2\",\"endsAt\":\"" + past + "\"}",
                "{\"delegateUserId\":\"m2\",\"endsAt\":\"" + tooLong + "\"}",
                "{\"endsAt\":\"" + future + "\"}"}) {
            mvc.perform(post("/api/approval/delegations").header("X-User-Id", "m1").header("X-User-Authorities", MANAGER)
                            .contentType(MediaType.APPLICATION_JSON).content(body))
                    .andExpect(status().isBadRequest());
        }
    }

    // ---------- oversight ----------

    @Test
    void oversightIsOnlyForTheTechnicalLeadPermission() throws Exception {
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "d1").header("X-User-Authorities", DEVELOPER))
                .andExpect(status().isForbidden());
        mvc.perform(get("/api/oversight/repositories").header("X-User-Id", "tl").header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].fullName").value("acme/shop"));
        mvc.perform(get("/api/oversight/repositories/{id}/pull-requests", repositoryId).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk());
        mvc.perform(get("/api/oversight/repositories/{id}/commits", UUID.randomUUID()).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isNotFound());
    }

    @Test
    void theTechnicalLeadReadsEveryWorkflowButOthersStillOnlySeeTheirOwn() throws Exception {
        mvc.perform(get("/api/document-workflows/history-accessible?page=0&size=20").header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(1))
                .andExpect(jsonPath("$.content[0].documentTitle").value("Shop guide"));
        mvc.perform(get("/api/document-workflows/{id}", workflowId).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk());
        mvc.perform(get("/api/document-workflows/{id}", workflowId).header("X-User-Id", "stranger")
                        .header("X-User-Authorities", DEVELOPER))
                .andExpect(status().isNotFound());
        // read-only: the Technical Lead permission does not let anyone decide a workflow
        mvc.perform(post("/api/document-workflows/{id}/approve", workflowId).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void theTechnicalLeadEditsTheDriftPoliciesOfAnyRepository() throws Exception {
        String rules = "[{\"scope\":\"REPOSITORY\",\"target\":\"\",\"onCommit\":true,\"onPullRequest\":false}]";
        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repositoryId).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD).contentType(MediaType.APPLICATION_JSON).content(rules))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].onCommit").value(true));
        mvc.perform(get("/api/oversight/repositories/{id}/drift-policies", repositoryId).header("X-User-Id", "tl")
                        .header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(jsonPath("$.length()").value(1));
        mvc.perform(put("/api/oversight/repositories/{id}/drift-policies", repositoryId).header("X-User-Id", "d1")
                        .header("X-User-Authorities", DEVELOPER).contentType(MediaType.APPLICATION_JSON).content(rules))
                .andExpect(status().isForbidden());
    }

    @Test
    void healthReportsCountsAndStatusBreakdowns() throws Exception {
        mvc.perform(get("/api/oversight/health").header("X-User-Id", "tl").header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.counts.repositories").value(1))
                .andExpect(jsonPath("$.counts.coveragePercent").value(0))
                .andExpect(jsonPath("$.repositoriesByStatus.CONNECTED").value(1))
                .andExpect(jsonPath("$.workflowsByStatus.PENDING_STAFF_REVIEW").value(1))
                .andExpect(jsonPath("$.graphTruncated").value(false));
        mvc.perform(get("/api/oversight/documentation").header("X-User-Id", "tl").header("X-User-Authorities", TECHNICAL_LEAD))
                .andExpect(status().isOk());
    }
}
