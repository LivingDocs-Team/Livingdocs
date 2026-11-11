package com.livingdocs.github.change;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ChangedEntityDetectorTest {

    private static final CodeEntity INVOICE = new CodeEntity("CLASS", "Invoice", 1, 9);
    private static final CodeEntity TOTAL = new CodeEntity("METHOD", "Invoice.total", 2, 4);

    @Test
    void classifiesAddedModifiedAndRemovedEntities() {
        List<CodeEntity> before = List.of(INVOICE, TOTAL, new CodeEntity("METHOD", "Invoice.discount", 6, 8));
        List<CodeEntity> after = List.of(INVOICE, TOTAL, new CodeEntity("METHOD", "Invoice.tax", 6, 8));

        assertThat(ChangedEntityDetector.detect(before, after, UnifiedDiff.parse(UnifiedDiffTest.PATCH))).containsExactly(
                new ChangedEntity("CLASS", "Invoice", "MODIFIED", 1, 9),
                new ChangedEntity("METHOD", "Invoice.total", "MODIFIED", 2, 4),
                new ChangedEntity("METHOD", "Invoice.tax", "ADDED", 6, 8),
                new ChangedEntity("METHOD", "Invoice.discount", "REMOVED", 6, 8));
    }

    @Test
    void entityOutsideTheChangedLinesIsNotReported() {
        // Chỉ sửa dòng 3 (trong total); method tax ở dòng 6-8 không đổi
        UnifiedDiff diff = UnifiedDiff.parse("@@ -2,3 +2,3 @@\n     int total() {\n-        return 1;\n+        return 2;\n     }");
        List<CodeEntity> entities = List.of(INVOICE, TOTAL, new CodeEntity("METHOD", "Invoice.tax", 6, 8));

        assertThat(ChangedEntityDetector.detect(entities, entities, diff)).extracting(ChangedEntity::name)
                .containsExactly("Invoice", "Invoice.total");
    }

    @Test
    void removingOneOfTwoMethodsWithTheSameNameIsAModification() {
        // Bản trước có hai latestOrSync (dòng 2-3 và 4-5), bản sau còn một (như bản vá PR #70)
        UnifiedDiff diff = UnifiedDiff.parse("@@ -1,7 +1,4 @@\n class S {\n   void latestOrSync() {\n   }\n"
                + "-  void latestOrSync() {\n-  }\n-\n }");
        List<CodeEntity> before = List.of(new CodeEntity("CLASS", "S", 1, 7),
                new CodeEntity("METHOD", "S.latestOrSync", 2, 3), new CodeEntity("METHOD", "S.latestOrSync", 4, 5));
        List<CodeEntity> after = List.of(new CodeEntity("CLASS", "S", 1, 4), new CodeEntity("METHOD", "S.latestOrSync", 2, 3));

        assertThat(ChangedEntityDetector.detect(before, after, diff)).containsExactly(
                new ChangedEntity("CLASS", "S", "MODIFIED", 1, 4),
                new ChangedEntity("METHOD", "S.latestOrSync", "MODIFIED", 2, 3));
    }
}
