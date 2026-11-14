package com.cnpm.backend.service;

import java.util.Map;
import java.util.Set;
import java.util.HashSet;
import java.util.stream.Collectors;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.repository.RoleRepository;

@Component
public class RoleCatalogInitializer implements ApplicationRunner {
    private static final Map<String, String> ROLES = Map.of(
            "DEVELOPER", "Develops and maintains the product",
            "STAFF", "Staff member",
            "MANAGER", "Manages team operations",
            "TECHNICAL_LEAD", "Leads technical work",
            "ADMINISTRATOR", "System administrator");
    private static final Map<String, String> PERMISSIONS = Map.ofEntries(
            Map.entry("USER_VIEW", "View user records"),
            Map.entry("USER_UPDATE", "Update user profile fields"),
            Map.entry("USER_DISABLE", "Enable or disable user accounts"),
            Map.entry("USER_ASSIGN_ROLE", "Assign a primary role to a user"),
            Map.entry("ROLE_VIEW", "View system roles"),
            Map.entry("PERMISSION_VIEW", "View system permissions"),
            Map.entry("ROLE_ASSIGN_PERMISSION", "Assign permissions to a role"),
            Map.entry("DOCUMENT_VIEW", "View owned documents and workflow history"),
            Map.entry("DOCUMENT_CREATE", "Create a business document"),
            Map.entry("DOCUMENT_UPDATE", "Edit a business document"),
            Map.entry("DOCUMENT_SUBMIT", "Submit a business document for processing"),
            Map.entry("DOCUMENT_REVIEW_QUEUE_VIEW", "View documents awaiting staff review"),
            Map.entry("DOCUMENT_CLAIM", "Accept a document for staff review"),
            Map.entry("DOCUMENT_RELEASE", "Release a document currently claimed by the assigned staff member"),
            Map.entry("DOCUMENT_REVIEW", "Inspect a document during staff review"),
            Map.entry("DOCUMENT_REASSIGN", "Reassign a claimed review to another active staff member"),
            Map.entry("DOCUMENT_APPROVAL_QUEUE_VIEW", "View documents awaiting manager approval"),
            Map.entry("DOCUMENT_APPROVE", "Approve a business document"),
            Map.entry("DOCUMENT_REJECT", "Reject a business document"),
            Map.entry("DOCUMENT_ROLLBACK", "Rollback an approved document to a previous version"),
            Map.entry("DOCUMENT_TECHNICAL_REVIEW", "Perform technical review of a document"));

    // Business workflow grants are enforced by the GitHub Integration document-workflow API.
    // TECHNICAL_LEAD is catalogued for the planned technical-review endpoint, which is not yet present.
    private static final Map<String, Set<String>> ROLE_PERMISSIONS = Map.of(
        "DEVELOPER", Set.of("DOCUMENT_VIEW", "DOCUMENT_CREATE", "DOCUMENT_UPDATE", "DOCUMENT_SUBMIT"),
        "STAFF", Set.of("DOCUMENT_REVIEW_QUEUE_VIEW", "DOCUMENT_CLAIM", "DOCUMENT_RELEASE", "DOCUMENT_REVIEW"),
        "MANAGER", Set.of(
                "DOCUMENT_APPROVAL_QUEUE_VIEW",
                "DOCUMENT_APPROVE",
                "DOCUMENT_REJECT",
                "DOCUMENT_ROLLBACK"
        ),
        "TECHNICAL_LEAD", Set.of("DOCUMENT_TECHNICAL_REVIEW"));
   private static final Set<String> ADMIN_DEFAULT_PERMISSIONS = PERMISSIONS.keySet().stream()
        .filter(code -> !code.equals("DOCUMENT_APPROVE")
                && !code.equals("DOCUMENT_REJECT")
                && !code.equals("DOCUMENT_ROLLBACK"))
        .collect(Collectors.toUnmodifiableSet());

    private final RoleRepository roles;
    private final PermissionRepository permissions;

    public RoleCatalogInitializer(RoleRepository roles, PermissionRepository permissions) {
        this.roles = roles;
        this.permissions = permissions;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        Set<String> newlyCreatedPermissions = new HashSet<>();
        PERMISSIONS.forEach((code, description) -> {
            if (permissions.findById(code).isEmpty()) {
                permissions.save(new Permission(code, description));
                newlyCreatedPermissions.add(code);
            }
        });
        Map<String, Permission> permissionByCode = permissions.findAll().stream()
                .collect(Collectors.toMap(Permission::getCode, permission -> permission));

        ROLES.forEach((name, description) -> {
            Role role = roles.findById(name).orElse(null);
            boolean created = role == null;
            if (created) role = new Role(name, description);
            assignInitialPermissions(role, created, newlyCreatedPermissions, permissionByCode);
            if (created || hasNewAssignment(role, name, newlyCreatedPermissions)) roles.save(role);
        });
        Role legacyAdmin = roles.findById("ADMIN").orElse(null);
        boolean legacyCreated = legacyAdmin == null;
        if (legacyCreated) legacyAdmin = new Role("ADMIN", "Legacy administrator role");
        assignInitialPermissions(legacyAdmin, legacyCreated, newlyCreatedPermissions, permissionByCode);
        if (legacyCreated || hasNewAssignment(legacyAdmin, "ADMIN", newlyCreatedPermissions)) roles.save(legacyAdmin);
    }

    private static void assignInitialPermissions(Role role, boolean created,
            Set<String> newlyCreated, Map<String, Permission> permissionsByCode) {
        Set<String> defaults = ROLE_PERMISSIONS.getOrDefault(role.getName(), Set.of());
        if (role.getName().equals("ADMINISTRATOR") || role.getName().equals("ADMIN")) {
            defaults = ADMIN_DEFAULT_PERMISSIONS;
        }
        Set<String> toAssign = created ? defaults : defaults.stream()
                .filter(newlyCreated::contains).collect(Collectors.toSet());
        toAssign.stream().map(permissionsByCode::get).filter(java.util.Objects::nonNull)
                .forEach(role.getPermissions()::add);
    }

    private static boolean hasNewAssignment(Role role, String roleName, Set<String> newlyCreated) {
        Set<String> defaults = ROLE_PERMISSIONS.getOrDefault(roleName, Set.of());
        if (roleName.equals("ADMINISTRATOR") || roleName.equals("ADMIN")) defaults = ADMIN_DEFAULT_PERMISSIONS;
        return defaults.stream().anyMatch(newlyCreated::contains);
    }
}



