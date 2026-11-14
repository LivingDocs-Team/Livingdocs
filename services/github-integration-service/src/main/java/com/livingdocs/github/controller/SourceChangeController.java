package com.livingdocs.github.controller;

import com.livingdocs.github.dto.SourceChangeResponse;
import com.livingdocs.github.service.RepositoryManagementService;
import com.livingdocs.github.service.SourceChangeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

/** LD-116 - thay đổi mã nguồn đã phát hiện, cho bước cập nhật tài liệu (LD-128) đọc. */
@RestController
@Tag(name = "Source Changes", description = "LD-116 - thay đổi mã nguồn phát hiện từ commit và Pull Request")
public class SourceChangeController {

    private final RepositoryManagementService repositoryService;
    private final SourceChangeService sourceChangeService;

    public SourceChangeController(RepositoryManagementService repositoryService,
                                  SourceChangeService sourceChangeService) {
        this.repositoryService = repositoryService;
        this.sourceChangeService = sourceChangeService;
    }

    @GetMapping("/api/repositories/{id}/source-changes")
    @Operation(summary = "Thay đổi mã nguồn đã phát hiện (tối đa 50, mới nhất trước)",
            description = "Mỗi phần tử là một commit trên nhánh mặc định hoặc một commit head của Pull Request, "
                    + "kèm file Java/Python thay đổi và code entity ADDED / MODIFIED / REMOVED.")
    public List<SourceChangeResponse> list(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        repositoryService.get(userId, id);  // 404 nếu không có repo, 403 nếu không thuộc người dùng
        return sourceChangeService.list(id);
    }

    @PostMapping("/api/repositories/{id}/source-changes/{changeId}/retry")
    @Operation(summary = "Chạy lại một source change FAILED",
            description = "409 SOURCE_CHANGE_NOT_FAILED nếu source change không ở trạng thái FAILED. "
                    + "204 nếu lần chạy lại không còn file mã nguồn nào thay đổi.")
    public ResponseEntity<SourceChangeResponse> retry(@RequestHeader(USER_HEADER) String userId,
                                                      @PathVariable UUID id, @PathVariable UUID changeId) {
        repositoryService.get(userId, id);
        return sourceChangeService.retry(id, changeId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.noContent().build());
    }
}



