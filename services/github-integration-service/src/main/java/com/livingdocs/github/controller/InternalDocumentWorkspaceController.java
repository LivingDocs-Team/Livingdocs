package com.livingdocs.github.controller;

import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@RestController
@RequestMapping("/api/internal/documents")
public class InternalDocumentWorkspaceController {

    private final JdbcTemplate jdbcTemplate;

    public InternalDocumentWorkspaceController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping("/{docId}/workspace")
    public Map<String, String> getWorkspaceOwner(
            @PathVariable String docId,
            @RequestHeader(value = "X-User-Id", required = false) String callerUserId) {

        if (callerUserId == null || callerUserId.isBlank()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Caller identity required");
        }

        try {
            // LƯU Ý: Thay "documents" và "workspace_id" bằng tên bảng/cột thực tế trong file V10 Flyway của bạn
            String sql = "SELECT workspace_id FROM documents WHERE id = ?";
            String workspaceId = jdbcTemplate.queryForObject(sql, String.class, docId);
            
            if (workspaceId == null || workspaceId.isBlank()) {
                throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Document has no workspace identity");
            }
            return Map.of("workspaceId", workspaceId);
            
        } catch (org.springframework.dao.EmptyResultDataAccessException e) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Document not found");
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Error querying database");
        }
    }
}