package com.livingdocs.github.change;

import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * LD-117/LD-120: trường "patch" GitHub trả về cho một file (unified diff, chỉ gồm các hunk "@@ ... @@").
 * Ghi lại dòng nào được thêm (theo số dòng file mới) và dòng nào bị xoá (theo số dòng file cũ).
 */
public final class UnifiedDiff {

    private static final Pattern HUNK = Pattern.compile("^@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@.*");

    private final List<Hunk> hunks;
    private final BitSet addedLines = new BitSet();      // số dòng (file mới) được thêm
    private final BitSet deletedLines = new BitSet();    // số dòng (file cũ) bị xoá
    private final BitSet deletionPoints = new BitSet();  // dòng (file mới) ngay sau chỗ có dòng bị xoá

    private UnifiedDiff(List<Hunk> hunks) {
        this.hunks = hunks;
        for (Hunk hunk : hunks) {
            int oldLine = hunk.oldStart();
            int newLine = hunk.newStart();
            for (String line : hunk.lines()) {
                char marker = line.isEmpty() ? ' ' : line.charAt(0);
                if (marker == '+') {
                    addedLines.set(newLine++);
                } else if (marker == '-') {
                    deletedLines.set(oldLine++);
                    deletionPoints.set(newLine);
                } else {
                    oldLine++;
                    newLine++;
                }
            }
        }
    }

    /** Đọc patch. Dòng "\ No newline at end of file" được bỏ qua. */
    public static UnifiedDiff parse(String patch) {
        List<Hunk> hunks = new ArrayList<>();
        Hunk current = null;
        for (String line : splitLines(patch == null ? "" : patch)) {
            Matcher header = HUNK.matcher(line);
            if (header.matches()) {
                int oldCount = count(header.group(2));
                int newCount = count(header.group(4));
                // Khi số dòng là 0, số đầu chỉ dòng ngay trước chỗ thay đổi
                int oldStart = Integer.parseInt(header.group(1)) + (oldCount == 0 ? 1 : 0);
                int newStart = Integer.parseInt(header.group(3)) + (newCount == 0 ? 1 : 0);
                current = new Hunk(oldStart, newStart, new ArrayList<>());
                hunks.add(current);
            } else if (current != null && !line.startsWith("\\")) {
                current.lines().add(line);
            }
        }
        return new UnifiedDiff(hunks);
    }

    /** Có dòng nào trong [start, end] của file mới được thêm, hoặc có dòng bị xoá nằm bên trong khoảng đó. */
    public boolean touchesNew(int start, int end) {
        int added = addedLines.nextSetBit(start);
        if (added >= 0 && added <= end) {
            return true;
        }
        int deletion = deletionPoints.nextSetBit(start + 1);
        return deletion >= 0 && deletion <= end;
    }

    /** Có dòng nào trong [start, end] của file cũ bị xoá. */
    public boolean touchesOld(int start, int end) {
        int deleted = deletedLines.nextSetBit(start);
        return deleted >= 0 && deleted <= end;
    }

    /** Dựng lại nội dung file cũ từ nội dung file mới và patch (không cần gọi thêm GitHub). */
    public String reconstructOld(String newContent) {
        List<String> newLines = newContent == null || newContent.isEmpty() ? List.of() : splitLines(newContent);
        StringBuilder old = new StringBuilder();
        int next = 1; // dòng tiếp theo của file mới chưa chép
        for (Hunk hunk : hunks) {
            for (; next < hunk.newStart() && next <= newLines.size(); next++) {
                old.append(newLines.get(next - 1)).append('\n');
            }
            for (String line : hunk.lines()) {
                char marker = line.isEmpty() ? ' ' : line.charAt(0);
                String text = line.isEmpty() ? "" : line.substring(1);
                if (marker == '+') {
                    next++;
                } else if (marker == '-') {
                    old.append(text).append('\n');
                } else {
                    old.append(text).append('\n');
                    next++;
                }
            }
        }
        for (; next <= newLines.size(); next++) {
            old.append(newLines.get(next - 1)).append('\n');
        }
        return old.toString();
    }

    private static int count(String value) {
        return value == null ? 1 : Integer.parseInt(value);
    }

    /** Tách dòng theo '\n'; '\n' cuối file không tạo thêm dòng rỗng. */
    private static List<String> splitLines(String text) {
        List<String> lines = new ArrayList<>(List.of(text.split("\n", -1)));
        if (!lines.isEmpty() && lines.get(lines.size() - 1).isEmpty()) {
            lines.remove(lines.size() - 1);
        }
        return lines;
    }

    private record Hunk(int oldStart, int newStart, List<String> lines) {
    }
}



