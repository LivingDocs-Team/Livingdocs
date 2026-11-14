package com.livingdocs.github.change;

/**
 * LD-120: một code entity bị thay đổi.
 *
 * @param change    ADDED, MODIFIED hoặc REMOVED
 * @param startLine dòng trong file sau thay đổi (REMOVED: dòng trong file trước thay đổi)
 */
public record ChangedEntity(String kind, String name, String change, int startLine, int endLine) {

    public static final String ADDED = "ADDED";
    public static final String MODIFIED = "MODIFIED";
    public static final String REMOVED = "REMOVED";
}



