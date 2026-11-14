package com.livingdocs.github.controller;

import com.livingdocs.github.dto.AddRepositoriesRequest;
import com.livingdocs.github.dto.AvailableRepositoryResponse;
import com.livingdocs.github.dto.RepositoryResponse;
import com.livingdocs.github.service.RepositoryManagementService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

@RestController
@Tag(name = "Repository Management", description = "Epic 3 - quản lý repository")
public class RepositoryController {

    private final RepositoryManagementService repositoryService;

    public RepositoryController(RepositoryManagementService repositoryService) {
        this.repositoryService = repositoryService;
    }

    @GetMapping("/api/github/repos/available")
    @Operation(summary = "Liệt kê repository có thể truy cập trên GitHub")
    public List<AvailableRepositoryResponse> available(
            @RequestHeader(USER_HEADER) String userId) {
        return repositoryService.listAvailable(userId);
    }

    @PostMapping("/api/workspaces/{workspaceId}/repositories")
    @Operation(summary = "Thêm repository vào workspace")
    public ResponseEntity<List<RepositoryResponse>> add(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable String workspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String verifiedWorkspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Access", required = false) String verifiedAccess,
            @Valid @RequestBody AddRepositoriesRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(repositoryService.addRepositories(
                        userId, workspaceId, request.githubRepoIds(), verifiedWorkspaceId, verifiedAccess));
    }


    @GetMapping("/api/workspaces/{workspaceId}/repositories")
    @Operation(summary = "Danh sách repo của workspace (trạng thái, nhánh mặc định, lần đồng bộ cuối)")
    public List<RepositoryResponse> list(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable String workspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String verifiedWorkspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Access", required = false) String verifiedAccess) {
        return repositoryService.listByWorkspace(userId, workspaceId, verifiedWorkspaceId, verifiedAccess);
    }

    @GetMapping("/api/repositories/{id}")
    @Operation(summary = "Chi tiết một repo")
    public RepositoryResponse get(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String verifiedWorkspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Access", required = false) String verifiedAccess) {
        return repositoryService.get(userId, id, verifiedWorkspaceId, verifiedAccess);
    }

    /** Internal lookup used by the Backend to verify managed workspace ownership before proxying ID routes. */
    @GetMapping("/api/internal/repositories/{id}/workspace")
    public WorkspaceIdentityResponse workspaceIdentity(
            @RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        return new WorkspaceIdentityResponse(repositoryService.getWorkspaceId(id));
    }

    @org.springframework.web.bind.annotation.PutMapping("/api/workspaces/{workspaceId}/repositories/{id}")
    @Operation(summary = "Reassign an existing repository association to another owned workspace")
    public RepositoryResponse reassign(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable String workspaceId,
            @PathVariable UUID id,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String verifiedTargetWorkspaceId,
            @RequestHeader(value = "X-Verified-Source-Workspace-Id", required = false) String verifiedSourceWorkspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Access", required = false) String verifiedAccess) {
        return repositoryService.reassignRepository(userId, workspaceId, id,
                verifiedTargetWorkspaceId, verifiedSourceWorkspaceId, verifiedAccess);
    }

    // Đồng bộ repo với GitHub (LD-63): xem RepositorySyncController

    @DeleteMapping("/api/repositories/{id}")
    @Operation(summary = "Ngắt kết nối (gỡ) repo khỏi workspace")
    public ResponseEntity<Void> disconnect(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id,
            @RequestHeader(value = "X-Verified-Workspace-Id", required = false) String verifiedWorkspaceId,
            @RequestHeader(value = "X-Verified-Workspace-Access", required = false) String verifiedAccess) {
        repositoryService.disconnect(userId, id, verifiedWorkspaceId, verifiedAccess);
        return ResponseEntity.noContent().build();
    }

    public record WorkspaceIdentityResponse(String workspaceId) { }
}



