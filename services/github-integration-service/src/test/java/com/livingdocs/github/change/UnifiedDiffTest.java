package com.livingdocs.github.change;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class UnifiedDiffTest {

    static final String BEFORE = String.join("\n",
            "public class Invoice {", "    int total() {", "        return 1;", "    }", "",
            "    int discount() {", "        return 0;", "    }", "}") + "\n";
    static final String AFTER = String.join("\n",
            "public class Invoice {", "    int total() {", "        return 2;", "    }", "",
            "    int tax() {", "        return 1;", "    }", "}") + "\n";
    static final String PATCH = String.join("\n",
            "@@ -1,9 +1,9 @@", " public class Invoice {", "     int total() {", "-        return 1;", "+        return 2;",
            "     }", " ", "-    int discount() {", "-        return 0;", "+    int tax() {", "+        return 1;", "     }", " }");

    @Test
    void addedLinesUseNewNumbers_andDeletedLinesUseOldNumbers() {
        UnifiedDiff diff = UnifiedDiff.parse(PATCH);

        assertThat(diff.touchesNew(3, 3)).isTrue();
        assertThat(diff.touchesNew(6, 7)).isTrue();
        assertThat(diff.touchesNew(2, 2)).isFalse();
        assertThat(diff.touchesNew(8, 9)).isFalse();
        assertThat(diff.touchesOld(3, 3)).isTrue();
        assertThat(diff.touchesOld(6, 7)).isTrue();
        assertThat(diff.touchesOld(8, 9)).isFalse();
    }

    @Test
    void deletionCountsOnlyWhenItIsInsideTheRange() {
        // Xoá dòng "c" (dòng 5 của file cũ), nằm giữa dòng 4 ("b") và dòng 5 ("d") của file mới
        UnifiedDiff diff = UnifiedDiff.parse("@@ -3,4 +3,3 @@\n a\n b\n-c\n d");

        assertThat(diff.touchesNew(1, 5)).isTrue();   // xoá bên trong
        assertThat(diff.touchesNew(1, 4)).isFalse();  // xoá ngay sau dòng cuối
        assertThat(diff.touchesNew(5, 6)).isFalse();  // xoá ngay trước dòng đầu
    }

    @Test
    void reconstructsOldContentFromNewContentAndPatch() {
        assertThat(UnifiedDiff.parse(PATCH).reconstructOld(AFTER)).isEqualTo(BEFORE);
        // Thêm '\n' vào cuối file: dòng "\ No newline at end of file" được bỏ qua
        assertThat(UnifiedDiff.parse("@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b")
                .reconstructOld("a\nb\n")).isEqualTo("a\nb\n");
    }

    @Test
    void reconstructsAddedAndRemovedFiles() {
        assertThat(UnifiedDiff.parse("@@ -0,0 +1,2 @@\n+a\n+b").reconstructOld("a\nb\n")).isEmpty();
        assertThat(UnifiedDiff.parse("@@ -1,2 +0,0 @@\n-a\n-b").reconstructOld("")).isEqualTo("a\nb\n");
    }
}
