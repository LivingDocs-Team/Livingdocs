package com.livingdocs.github.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;

/** A custom documentation template; the AI service validates the values. */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record DocumentationTemplateRequest(
        String name, String description, String instructions, List<String> sections) {
}
