package com.cnpm.backend.controller;

import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import com.cnpm.backend.entity.Permission;
import com.cnpm.backend.entity.Role;
import com.cnpm.backend.repository.PermissionRepository;
import com.cnpm.backend.repository.RoleRepository;

@RestController
@RequestMapping("/api/admin")
public class AdminRoleController {
    private static final Set<String> FIXED_ROLES = Set.of("DEVELOPER", "STAFF", "MANAGER", "TECHNICAL_LEAD", "ADMINISTRATOR", "ADMIN");
    private static final Set<String> ADMIN_PERMISSIONS = Set.of("USER_VIEW", "USER_UPDATE", "USER_DISABLE", "USER_ASSIGN_ROLE", "ROLE_VIEW", "PERMISSION_VIEW", "ROLE_ASSIGN_PERMISSION", "DOCUMENT_REASSIGN");
    private final RoleRepository roles;
    private final PermissionRepository permissions;

    public AdminRoleController(RoleRepository roles, PermissionRepository permissions) {
        this.roles = roles;
        this.permissions = permissions;
    }

    @GetMapping("/roles")
    @PreAuthorize("hasAuthority('ROLE_VIEW')")
    @Transactional(readOnly = true)
    public List<RoleResponse> listRoles() {
        return roles.findAll().stream().map(AdminRoleController::toResponse).toList();
    }

    @GetMapping("/roles/{name}")
    @PreAuthorize("hasAuthority('ROLE_VIEW')")
    @Transactional(readOnly = true)
    public RoleResponse getRole(@PathVariable String name) {
        return toResponse(findRole(name));
    }

    @PatchMapping("/roles/{name}")
    @PreAuthorize("hasAuthority('ROLE_ASSIGN_PERMISSION')")
    @Transactional
    public RoleResponse updateRole(@PathVariable String name, @RequestBody UpdateRoleRequest request) {
        Role role = findRole(name);
        if (request == null || request.description() == null || request.description().isBlank() || request.description().length() > 120) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Description must contain 1 to 120 characters");
        }
        role.setDescription(request.description().trim());
        return toResponse(roles.save(role));
    }

    @GetMapping("/permissions")
    @PreAuthorize("hasAuthority('PERMISSION_VIEW')")
    @Transactional(readOnly = true)
    public List<PermissionResponse> listPermissions() {
        return permissions.findAll().stream().map(p -> new PermissionResponse(p.getCode(), p.getDescription())).toList();
    }

    @GetMapping("/permissions/{code}")
    @PreAuthorize("hasAuthority('PERMISSION_VIEW')")
    @Transactional(readOnly = true)
    public PermissionResponse getPermission(@PathVariable String code) {
        Permission p = permissions.findById(code.toUpperCase(Locale.ROOT))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Permission not found"));
        return new PermissionResponse(p.getCode(), p.getDescription());
    }

    @PutMapping("/roles/{name}/permissions")
    @PreAuthorize("hasAuthority('ROLE_ASSIGN_PERMISSION')")
    @Transactional
    public RoleResponse replacePermissions(@PathVariable String name, @RequestBody PermissionAssignment request) {
        Role role = findRole(name);
        if (request == null || request.permissionCodes() == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "permissionCodes is required");
        }
        Set<String> codes = request.permissionCodes().stream().map(c -> c.toUpperCase(Locale.ROOT)).collect(Collectors.toSet());
        List<Permission> found = permissions.findAllById(codes);
        if (found.size() != codes.size()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "One or more permissions do not exist");
        }
        if ((role.getName().equals("ADMINISTRATOR") || role.getName().equals("ADMIN")) && !codes.containsAll(ADMIN_PERMISSIONS)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Administrator permissions cannot be removed");
        }
        role.getPermissions().clear();
        role.getPermissions().addAll(found);
        return toResponse(roles.save(role));
    }

    private Role findRole(String name) {
        String normalized = name.toUpperCase(Locale.ROOT);
        if (!FIXED_ROLES.contains(normalized)) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Role not found");
        return roles.findById(normalized).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Role catalog has not been initialized"));
    }

    private static RoleResponse toResponse(Role role) {
        return new RoleResponse(role.getName(), role.getDescription(),
                role.getPermissions().stream().map(Permission::getCode).sorted().toList());
    }
    public record UpdateRoleRequest(String description) { }
    public record PermissionAssignment(List<String> permissionCodes) { }
    public record RoleResponse(String name, String description, List<String> permissions) { }
    public record PermissionResponse(String code, String description) { }
}
