package com.livingdocs.github.controller;

import com.livingdocs.github.dto.CommitResponse;
import com.livingdocs.github.dto.PullRequestResponse;
import com.livingdocs.github.service.IngestionService;
import com.livingdocs.github.service.RepositoryManagementService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

import static com.livingdocs.github.controller.GitHubConnectionController.USER_HEADER;

/** LD-68 - xem Pull Request và commit đã nhận của một repository (màn hình "PR & Commit List"). */
@RestController
@Tag(name = "Repository Activity", description = "LD-68 - Pull Request và commit đã nhận")
public class RepositoryActivityController {

    private final RepositoryManagementService repositoryService;
    private final IngestionService ingestionService;

    public RepositoryActivityController(RepositoryManagementService repositoryService,
                                        IngestionService ingestionService) {
        this.repositoryService = repositoryService;
        this.ingestionService = ingestionService;
    }

    @GetMapping("/api/repositories/{id}/pull-requests")
    @Operation(summary = "Pull Request đã nhận (tối đa 100, cập nhật gần nhất trước)")
    public List<PullRequestResponse> pullRequests(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        repositoryService.get(userId, id);  // 404 nếu không có repo, 403 nếu không thuộc người dùng
        return ingestionService.listPullRequests(id);
    }

    @GetMapping("/api/repositories/{id}/commits")
    @Operation(summary = "Commit đã nhận (tối đa 100, mới nhất trước)")
    public List<CommitResponse> commits(@RequestHeader(USER_HEADER) String userId, @PathVariable UUID id) {
        repositoryService.get(userId, id);
        return ingestionService.listCommits(id);
    }
}



