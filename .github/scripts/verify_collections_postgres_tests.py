"""Xác nhận các test Documentation Collections đã thật sự chạy trên PostgreSQL.

Các test này bị bỏ qua (skipped) khi thiếu COLLECTIONS_TEST_DB_URL, và Maven vẫn báo thành công.
Script đọc báo cáo Surefire của từng lớp test, so số test đã chạy với số phương thức @Test
trong mã nguồn, và thất bại nếu có test bị bỏ qua, lỗi hoặc thiếu báo cáo.
Kết quả từng test được ghi vào GitHub step summary (nếu có) để lưu làm bằng chứng.
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SERVICE = Path("services/github-integration-service")
SOURCES = SERVICE / "src/test/java/com/livingdocs/github"
REPORTS = SERVICE / "target/surefire-reports"
PACKAGE = "com.livingdocs.github"


def main() -> int:
    classes = sorted(p.stem for p in SOURCES.glob("DocumentationCollections*PostgresTest.java"))
    if not classes:
        print("Không tìm thấy lớp test DocumentationCollections*PostgresTest.")
        return 1
    problems, rows = [], []
    for name in classes:
        expected = len(re.findall(r"^\s*@Test\b", (SOURCES / f"{name}.java").read_text(encoding="utf-8"), re.M))
        report = REPORTS / f"TEST-{PACKAGE}.{name}.xml"
        if not report.is_file():
            problems.append(f"{name}: thiếu báo cáo {report}")
            continue
        suite = ET.parse(report).getroot()
        for case in suite.iter("testcase"):
            status = "passed"
            for tag in ("skipped", "failure", "error"):
                if case.find(tag) is not None:
                    status = tag
            rows.append((name, case.get("name"), case.get("time"), status))
        ran = [r for r in rows if r[0] == name]
        not_passed = [r for r in ran if r[3] != "passed"]
        if len(ran) != expected:
            problems.append(f"{name}: chạy {len(ran)} test, mã nguồn có {expected} phương thức @Test")
        for r in not_passed:
            problems.append(f"{name}.{r[1]}: {r[3]}")

    lines = ["### Documentation Collections — PostgreSQL", "", "| Lớp | Test | Thời gian (s) | Kết quả |", "|---|---|---|---|"]
    lines += [f"| {c} | {t} | {s} | {st} |" for c, t, s, st in rows]
    if problems:
        lines += ["", "**Không đạt:**"] + [f"- {p}" for p in problems]
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
