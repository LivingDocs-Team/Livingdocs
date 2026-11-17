package com.livingdocs.github.controller;

import com.livingdocs.github.dto.AuthorizeUrlResponse;
import com.livingdocs.github.dto.CallbackResponse;
import com.livingdocs.github.dto.ConnectionResponse;
import com.livingdocs.github.entity.GitHubConnection;
import com.livingdocs.github.exception.ApiException;
import com.livingdocs.github.exception.GitHubApiException;
import com.livingdocs.github.service.GitHubConnectionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

import java.net.URI;

@RestController
@RequestMapping("/api/github")
@Tag(name = "GitHub Connection", description = "Epic 2 - kết nối tài khoản GitHub")
public class GitHubConnectionController {

    static final String USER_HEADER = "X-User-Id";
    /** Mã lỗi khi người dùng bấm "Cancel" trên trang cấp quyền của GitHub. */
    static final String ACCESS_DENIED_CODE = "GITHUB_ACCESS_DENIED";

    private static final Logger log = LoggerFactory.getLogger(GitHubConnectionController.class);

    private final GitHubConnectionService connectionService;
    /** Trang frontend nhận kết quả kết nối (app.frontend-url). Rỗng thì callback trả JSON. */
    private final String frontendUrl;

    public GitHubConnectionController(GitHubConnectionService connectionService,
                                      @Value("${app.frontend-url:}") String frontendUrl) {
        this.connectionService = connectionService;
        this.frontendUrl = frontendUrl == null ? "" : frontendUrl.trim();
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
            description = "URL này phải trùng với Redirect URI khai báo trong GitHub App. "
                    + "Nếu có cấu hình FRONTEND_URL (app.frontend-url), người dùng được chuyển về frontend: "
                    + "thành công thì thêm ?github=connected&login=<tài khoản GitHub>, "
                    + "lỗi thì thêm ?github=error&reason=<mã lỗi>. Không cấu hình thì trả JSON.")
    public ResponseEntity<CallbackResponse> callback(@RequestParam(required = false) String code,
                                                     @RequestParam(required = false) String state,
                                                     @RequestParam(required = false) String error) {
        if (frontendUrl.isEmpty()) {
            GitHubConnection connection = connect(code, state, error);
            return ResponseEntity.ok(new CallbackResponse("Kết nối GitHub thành công", connection.getGithubLogin()));
        }
        URI target;
        try {
            GitHubConnection connection = connect(code, state, error);
            target = frontendUri("connected", "login", connection.getGithubLogin());
        } catch (ApiException e) {
            target = frontendUri("error", "reason", e.getCode());
        } catch (GitHubApiException e) {
            log.warn("GitHub callback failed: {}", e.getMessage());
            target = frontendUri("error", "reason", "GITHUB_API_ERROR");
        }
        return ResponseEntity.status(HttpStatus.FOUND).location(target).build();
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

    /** GitHub gửi ?error=access_denied (không có code) khi người dùng không cho phép. */
    private GitHubConnection connect(String code, String state, String error) {
        if (error != null && !error.isBlank() && (code == null || code.isBlank())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, ACCESS_DENIED_CODE,
                    "Bạn chưa cho phép LivingDocs truy cập GitHub. Hãy bấm 'Kết nối GitHub' lại nếu muốn kết nối.");
        }
        return connectionService.handleCallback(code, state);
    }

    private URI frontendUri(String result, String key, String value) {
        return UriComponentsBuilder.fromUriString(frontendUrl)
                .queryParam("github", result)
                .queryParam(key, value)
                .encode()
                .build()
                .toUri();
    }
}
