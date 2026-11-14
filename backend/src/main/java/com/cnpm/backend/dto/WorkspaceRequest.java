package com.cnpm.backend.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import com.fasterxml.jackson.annotation.JsonAnySetter;

/** Workspace input intentionally rejects fields outside the public API contract. */
public class WorkspaceRequest {

    @NotBlank
    @Size(max = 100)
    private String name;

    @Size(max = 1000)
    private String description;

    public WorkspaceRequest() {
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    @JsonAnySetter
    public void rejectUnsupportedField(String field, Object value) {
        throw new IllegalArgumentException("Unsupported workspace field: " + field);
    }
}



