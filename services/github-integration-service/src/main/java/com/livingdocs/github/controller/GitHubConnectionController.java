package com.livingdocs.github.controller;

import com.livingdocs.github.dto.AuthorizeUrlResponse;
import com.livingdocs.github.dto.CallbackResponse;
import com.livingdocs.github.dto.ConnectionResponse;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.service.GitHubConnectionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/github")
@Tag(name = "GitHub Connection", description = "Epic 2 - kết nối tài khoản GitHub")
public class GitHubConnectionController {

    static final String USER_HEADER = "X-User-Id";

    private final GitHubConnectionService connectionService;

    public GitHubConnectionController(GitHubConnectionService connectionService) {
        this.connectionService = connectionService;
    }

    @GetMapping("/authorize-url")
    @Operation(summary = "Tạo link để người dùng kết nối GitHub",
            description = "Frontend mở authorizeUrl (hoặc installUrl nếu chưa cài app) trong trình duyệt.")
    public AuthorizeUrlResponse authorizeUrl(
            @Parameter(description = "ID người dùng (tạm thời, sẽ thay bằng JWT)")
            @RequestHeader(USER_HEADER) String userId) {
        return connectionService.createAuthorizeUrl(userId);
    }

    @GetMapping("/callback")
    @Operation(summary = "GitHub gọi về sau khi người dùng cho phép",
            description = "URL này phải trùng với Redirect URI khai báo trong GitHub App.")
    public CallbackResponse callback(@RequestParam(required = false) String code,
                                     @RequestParam(required = false) String state) {
        GitHubConnection connection = connectionService.handleCallback(code, state);
        return new CallbackResponse("Kết nối GitHub thành công", connection.getGithubLogin());
    }

    @GetMapping("/connection")
    @Operation(summary = "Xem trạng thái kết nối GitHub")
    public ConnectionResponse status(@RequestHeader(USER_HEADER) String userId) {
        return connectionService.getStatus(userId);
    }

    @DeleteMapping("/connection")
    @Operation(summary = "Ngắt kết nối GitHub (thu hồi token)")
    public ResponseEntity<Void> revoke(@RequestHeader(USER_HEADER) String userId) {
        connectionService.revoke(userId);
        return ResponseEntity.noContent().build();
    }
}
