package com.cnpm.backend.controller;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.service.SystemConfigurationService;
import com.cnpm.backend.service.SystemConfigurationService.GroupView;

/** LD-273: administrators view and change the system configuration (see SystemConfigurationService for the settings). */
@RestController
@RequestMapping("/api/admin/system-configuration")
public class AdminSystemConfigurationController {
    private final SystemConfigurationService configuration;

    public AdminSystemConfigurationController(SystemConfigurationService configuration) {
        this.configuration = configuration;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('SYSTEM_CONFIG_VIEW')")
    public List<GroupView> listGroups() {
        return configuration.getAll();
    }

    @GetMapping("/{group}")
    @PreAuthorize("hasAuthority('SYSTEM_CONFIG_VIEW')")
    public GroupView getGroup(@PathVariable String group) {
        return configuration.getGroup(group);
    }

    @PatchMapping("/{group}")
    @PreAuthorize("hasAuthority('SYSTEM_CONFIG_UPDATE')")
    public GroupView updateGroup(@PathVariable String group, @RequestBody UpdateRequest request,
            Authentication authentication) {
        if (request == null || request.settings() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "settings is required");
        }
        return configuration.update(group, request.settings(), authentication.getName());
    }

    @DeleteMapping("/{group}")
    @PreAuthorize("hasAuthority('SYSTEM_CONFIG_UPDATE')")
    public GroupView resetGroup(@PathVariable String group) {
        return configuration.reset(group);
    }

    public record UpdateRequest(Map<String, Object> settings) { }
}

