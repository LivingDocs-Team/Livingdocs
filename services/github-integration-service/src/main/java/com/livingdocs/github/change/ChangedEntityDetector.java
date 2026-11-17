package com.livingdocs.github.change;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * LD-120: tìm code entity bị thay đổi trong một file bằng cách so khoảng dòng của entity
 * (do Code Analyzer trả về) với các dòng được thêm/xoá trong diff.
 * Entity bị chạm tới mà chỉ có ở bản sau là ADDED, có ở cả hai bản là MODIFIED, chỉ có ở bản trước là REMOVED.
 */
public final class ChangedEntityDetector {

    private ChangedEntityDetector() {
    }

    public static List<ChangedEntity> detect(List<CodeEntity> before, List<CodeEntity> after, UnifiedDiff diff) {
        Set<String> beforeKeys = before.stream().map(CodeEntity::key).collect(Collectors.toSet());
        Set<String> afterKeys = after.stream().map(CodeEntity::key).collect(Collectors.toSet());
        Map<String, ChangedEntity> changed = new LinkedHashMap<>();

        for (CodeEntity entity : after) {
            if (diff.touchesNew(entity.startLine(), entity.endLine())) {
                String change = beforeKeys.contains(entity.key()) ? ChangedEntity.MODIFIED : ChangedEntity.ADDED;
                changed.putIfAbsent(entity.key(), changedEntity(entity, change));
            }
        }
        for (CodeEntity entity : before) {
            if (!diff.touchesOld(entity.startLine(), entity.endLine())) {
                continue;
            }
            if (afterKeys.contains(entity.key())) {
                // Vẫn còn ở bản sau (ví dụ chỉ xoá vài dòng bên trong): MODIFIED, báo vị trí ở bản sau
                changed.putIfAbsent(entity.key(), changedEntity(find(after, entity.key()), ChangedEntity.MODIFIED));
            } else {
                changed.putIfAbsent(entity.key(), changedEntity(entity, ChangedEntity.REMOVED));
            }
        }
        return new ArrayList<>(changed.values());
    }

    private static CodeEntity find(List<CodeEntity> entities, String key) {
        return entities.stream().filter(e -> e.key().equals(key)).findFirst().orElseThrow();
    }

    private static ChangedEntity changedEntity(CodeEntity entity, String change) {
        return new ChangedEntity(entity.kind(), entity.name(), change, entity.startLine(), entity.endLine());
    }
}
