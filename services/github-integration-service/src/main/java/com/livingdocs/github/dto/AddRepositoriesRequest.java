package com.livingdocs.github.dto;

import jakarta.validation.constraints.NotEmpty;

import java.util.List;

public record AddRepositoriesRequest(
        @NotEmpty(message = "phải chọn ít nhất 1 repository") List<Long> githubRepoIds) {
}
