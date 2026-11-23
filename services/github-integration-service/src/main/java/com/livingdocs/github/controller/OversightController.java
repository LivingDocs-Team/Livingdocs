package com.livingdocs.github.controller;

import com.livingdocs.github.change.AutoUpdatePolicies;
import com.livingdocs.github.dto.DocumentationArtifactResponse;
import com.livingdocs.github.service.OversightService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Read-only views for the Technical Lead and Administrator, plus the drift (auto-update) policies. */
@RestController
@RequestMapping("/api/oversight")
public class OversightController {
    private final OversightService oversight;

    public OversightController(OversightService oversight) {
        this.oversight = oversight;
    }

    private static Set<String> authorities(String header) {
        return Arrays.stream(header.split(",")).map(String::trim).filter((value) -> !value.isEmpty())
                .collect(Collectors.toSet());
    }

    private static void check(String header) {
        OversightService.require(authorities(header));
    }

    @GetMapping("/repositories")
    public List<OversightService.RepositorySummary> repositories(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities) {
        check(authorities);
        return oversight.repositories();
    }

    @GetMapping("/repositories/{id}/pull-requests")
    public Object pullRequests(@RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities,
            @PathVariable UUID id) {
        check(authorities);
        return oversight.pullRequests(id);
    }

    @GetMapping("/repositories/{id}/commits")
    public Object commits(@RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities,
            @PathVariable UUID id) {
        check(authorities);
        return oversight.commits(id);
    }

    @GetMapping("/repositories/{id}/drift-policies")
    public List<AutoUpdatePolicies.Rule> driftPolicies(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        check(authorities);
        return oversight.driftPolicies(id);
    }

    @PutMapping("/repositories/{id}/drift-policies")
    public List<AutoUpdatePolicies.Rule> replaceDriftPolicies(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities, @PathVariable UUID id,
            @RequestBody List<AutoUpdatePolicies.Rule> rules) {
        check(authorities);
        return oversight.replaceDriftPolicies(id, rules);
    }

    @GetMapping("/documentation")
    public List<OversightService.DocumentSummary> documents(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities) {
        check(authorities);
        return oversight.documents();
    }

    @GetMapping("/documentation/{id}")
    public DocumentationArtifactResponse document(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        check(authorities);
        return oversight.document(id);
    }

    @GetMapping("/health")
    public OversightService.Health health(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities) {
        check(authorities);
        return oversight.health();
    }
}
