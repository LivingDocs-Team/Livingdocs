package com.livingdocs.github.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.service.ApprovalDelegationService;
import com.livingdocs.github.service.ApprovalPolicyService;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpStatus;

import java.util.Arrays;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** Approval and merge policies and Manager delegations. Managers (and Administrators) manage them. */
@RestController
@RequestMapping("/api/approval")
public class ApprovalGovernanceController {
    private final ApprovalPolicyService policies;
    private final ApprovalDelegationService delegations;

    public ApprovalGovernanceController(ApprovalPolicyService policies, ApprovalDelegationService delegations) {
        this.policies = policies;
        this.delegations = delegations;
    }

    private static void requireManager(String header) {
        Set<String> authorities = Arrays.stream(header.split(",")).map(String::trim).collect(Collectors.toSet());
        if (!authorities.contains("ROLE_MANAGER") && !authorities.contains("ROLE_ADMINISTRATOR")
                && !authorities.contains("ROLE_ADMIN")) {
            throw ApiException.forbidden("Manager access is required.");
        }
    }

    @GetMapping("/policies/{type}")
    public ApprovalPolicyService.PolicyView policy(
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities, @PathVariable String type) {
        requireManager(authorities);
        return policies.view(type);
    }

    @PutMapping("/policies/{type}")
    public ApprovalPolicyService.PolicyView replacePolicy(
            @RequestHeader(DocumentWorkflowController.USER_HEADER) String actor,
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities,
            @PathVariable String type, @RequestBody JsonNode body) {
        requireManager(authorities);
        return policies.replace(actor, type, body);
    }

    @GetMapping("/delegations")
    public ApprovalDelegationService.Delegations delegations(
            @RequestHeader(DocumentWorkflowController.USER_HEADER) String actor,
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities) {
        requireManager(authorities);
        return delegations.list(actor);
    }

    @PostMapping("/delegations")
    @ResponseStatus(HttpStatus.CREATED)
    public ApprovalDelegationService.Delegation createDelegation(
            @RequestHeader(DocumentWorkflowController.USER_HEADER) String actor,
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities,
            @RequestBody ApprovalDelegationService.CreateRequest request) {
        requireManager(authorities);
        return delegations.create(actor, request);
    }

    @DeleteMapping("/delegations/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void revokeDelegation(@RequestHeader(DocumentWorkflowController.USER_HEADER) String actor,
            @RequestHeader(DocumentWorkflowController.AUTHORITIES_HEADER) String authorities, @PathVariable UUID id) {
        requireManager(authorities);
        delegations.revoke(actor, id);
    }
}
