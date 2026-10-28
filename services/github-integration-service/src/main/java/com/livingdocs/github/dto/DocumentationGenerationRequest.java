package com.livingdocs.github.dto;

/** Optional AI generation settings; omitted values use the AI service defaults. */
public record DocumentationGenerationRequest(String templateId, String outputLanguage) {
}
