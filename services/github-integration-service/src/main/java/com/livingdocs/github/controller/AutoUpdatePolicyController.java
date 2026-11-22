package com.livingdocs.github.controller;

import com.livingdocs.github.change.AutoUpdatePolicies;
import com.livingdocs.github.change.AutoUpdatePolicies.Rule;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/repositories/{id}/auto-update-policies")
public class AutoUpdatePolicyController {
    private final AutoUpdatePolicies policies;

    public AutoUpdatePolicyController(AutoUpdatePolicies policies) {
        this.policies = policies;
    }

    @GetMapping
    public List<Rule> get(@PathVariable UUID id, @RequestHeader("X-User-Id") String actor,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String workspace) {
        return policies.get(actor, workspace, id);
    }

    @PutMapping
    public List<Rule> replace(@PathVariable UUID id, @RequestHeader("X-User-Id") String actor,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String workspace,
            @RequestBody List<Rule> rules) {
        return policies.replace(actor, workspace, id, rules);
    }
}
