package com.livingdocs.github.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.UUID;

public record ReplaceDocumentationCodeLinksRequest(@NotNull @Size(max = 500) List<UUID> codeEntityIds) { }
