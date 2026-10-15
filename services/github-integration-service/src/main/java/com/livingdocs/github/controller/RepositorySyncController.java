package com.livingdocs.github.controller;

import com.livingdocs.github.dto.SyncRequest;
import com.livingdocs.github.dto.SyncResultResponse;
import com.livingdocs.github.service.RepositorySyncService;
import com.livingdocs.github.sync.AnalysisInput;
import com.livingdocs.github.sync.SyncOptions;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

/**
 * LD-63 - đồng bộ repository với GitHub. Lỗi (repo không tồn tại, hết lượt gọi API...) do
 * GlobalExceptionHandler trả về, bảng mã lỗi xem docs/repository-sync-contract.md mục 4.
 */
@RestController
@Tag(name = "Repository Sync", description = "LD-63 - đồng bộ repository với GitHub")
public class RepositorySyncController {

    private final RepositorySyncService syncService;

    public RepositorySyncController(RepositorySyncService syncService) {
        this.syncService = syncService;
    }

    @PostMapping("/api/repositories/{id}/sync")
    @Operation(summary = "Đồng bộ repository với GitHub",
            description = "Lấy thông tin repo, commit mới nhất, danh sách file và nội dung file java/python. "
                    + "Body không bắt buộc: bỏ trống hoặc {} là đồng bộ nhánh mặc định, tối đa 200 file. "
                    + "Response không kèm nội dung file (lấy ở /sync/latest/analysis-input).")
    public SyncResultResponse sync(
            @RequestHeader(USER_HEADER) String userId,
            @PathVariable UUID id,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = false, content = @Content(
                    mediaType = "application/json",
                    schema = @Schema(implementation = SyncRequest.class),
                    examples = {
                            @ExampleObject(name = "Mặc định", summary = "Nhánh mặc định, tối đa 200 file", value = "{}"),
                            @ExampleObject(name = "Chọn nhánh", summary = "Nhánh develop, tối đa 50 file",
                                    value = "{\"branch\": \"develop\", \"maxFiles\": 50}")}))
            @RequestBody(required = false) SyncRequest request) {
        SyncOptions options = request == null ? SyncOptions.defaults() : request.toOptions();
        return SyncResultResponse.from(syncService.sync(userId, id, options));
    }

    @GetMapping("/api/repositories/{id}/sync/latest")
    @Operation(summary = "Kết quả lần đồng bộ gần nhất (không kèm nội dung file)")
    public SyncResultResponse latest(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        return SyncResultResponse.from(syncService.latest(userId, id));
    }

    @GetMapping("/api/repositories/{id}/sync/latest/analysis-input")
    @Operation(summary = "Dữ liệu gửi sang service phân tích code (LD-328)",
            description = "Body cho POST /api/v1/analyze-repo: các file đã tải được nội dung, kèm nội dung.")
    public AnalysisInput analysisInput(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        return AnalysisInput.from(syncService.latest(userId, id));
    }
}
