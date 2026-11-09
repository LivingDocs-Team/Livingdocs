package com.cnpm.backend.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record WorkspaceMemberRequest(@NotNull @Positive Long userId) { }
