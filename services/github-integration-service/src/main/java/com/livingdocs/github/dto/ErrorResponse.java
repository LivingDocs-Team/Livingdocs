package com.livingdocs.github.dto;

import java.time.Instant;

public record ErrorResponse(int status, String code, String message, Instant timestamp) {
}
