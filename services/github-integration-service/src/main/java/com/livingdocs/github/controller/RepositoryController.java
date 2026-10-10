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
    @Operation(summary = "Liệt kê repo trên GitHub mà người dùng có thể thêm")
    public List<AvailableRepositoryResponse> available(@RequestHeader(USER_HEADER) String userId) {
        return repositoryService.listAvailable(userId);
    }

    @PostMapping("/api/workspaces/{workspaceId}/repositories")
    @Operation(summary = "Thêm một hoặc nhiều repo vào workspace")
    public ResponseEntity<List<RepositoryResponse>> add(@RequestHeader(USER_HEADER) String userId,
                                                        @PathVariable String workspaceId,
                                                        @Valid @RequestBody AddRepositoriesRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(repositoryService.addRepositories(userId, workspaceId, request.githubRepoIds()));
    }

    @GetMapping("/api/workspaces/{workspaceId}/repositories")
    @Operation(summary = "Danh sách repo của workspace (trạng thái, nhánh mặc định, lần đồng bộ cuối)")
    public List<RepositoryResponse> list(@PathVariable String workspaceId) {
        return repositoryService.listByWorkspace(workspaceId);
    }

    @GetMapping("/api/repositories/{id}")
    @Operation(summary = "Chi tiết một repo")
    public RepositoryResponse get(@PathVariable UUID id) {
        return repositoryService.get(id);
    }

    @PostMapping("/api/repositories/{id}/sync")
    @Operation(summary = "Đồng bộ lại repo thủ công")
    public RepositoryResponse sync(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        return repositoryService.sync(userId, id);
    }

    @DeleteMapping("/api/repositories/{id}")
    @Operation(summary = "Ngắt kết nối (gỡ) repo khỏi workspace")
    public ResponseEntity<Void> disconnect(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        repositoryService.disconnect(userId, id);
        return ResponseEntity.noContent().build();
    }
}
