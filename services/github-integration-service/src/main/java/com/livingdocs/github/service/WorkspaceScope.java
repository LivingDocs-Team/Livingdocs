package com.livingdocs.github.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Which managed workspaces the authenticated caller belongs to. The Backend (BFF) appends one
 * {@code WORKSPACE:<id>} entry per workspace to {@code X-User-Authorities}, or {@code WORKSPACE:*} for an
 * administrator. Personal workspaces ({@code ws-<userId>}) are the shared review pool: submitting a document
 * from one is what puts it in front of Staff and Managers, so only managed workspaces
 * ({@code workspace-<uuid>}) are isolated.
 */
public final class WorkspaceScope {
    public static final String PREFIX = "WORKSPACE:";
    public static final String ALL = PREFIX + "*";
    static final String MANAGED_PREFIX = "workspace-";

    private WorkspaceScope() { }

    public static boolean isManaged(String workspaceId) {
        return workspaceId != null && workspaceId.startsWith(MANAGED_PREFIX);
    }

    public static boolean allows(Set<String> authorities, String workspaceId) {
        if (!isManaged(workspaceId)) return true;
        return authorities.contains(ALL) || authorities.contains(PREFIX + workspaceId);
    }

    /**
     * Access to a repository, and so to its documents, pull requests, commits and policies. Stricter than
     * {@link #allows}: a personal workspace is private to its owner (it is not a shared review pool for
     * repositories), a managed workspace needs a {@code WORKSPACE:<id>} entry, and an unknown workspace is denied.
     */
    public static boolean allowsRepository(Set<String> authorities, String actor, String workspaceId) {
        if (workspaceId == null || workspaceId.isBlank()) return false;
        if (all(authorities) || authorities.contains(PREFIX + workspaceId)) return true;
        return actor != null && workspaceId.equals("ws-" + actor);
    }

    public static boolean all(Set<String> authorities) {
        return authorities.contains(ALL);
    }

    /** Never empty, so it is safe in a JPQL {@code in} clause. */
    public static List<String> workspaces(Set<String> authorities) {
        List<String> ids = new ArrayList<>();
        for (String authority : authorities) {
            if (authority.startsWith(PREFIX) && authority.length() > PREFIX.length() && !authority.equals(ALL)) {
                ids.add(authority.substring(PREFIX.length()));
            }
        }
        if (ids.isEmpty()) ids.add("-");
        return ids;
    }
}
