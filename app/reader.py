import os
from app.models import FileAnalysis
from pathlib import Path

class FileReader:
    @staticmethod
    def detect_language(path: str):
        suffix = Path(path).suffix.lower()
        mapping = {
            ".py": "python",
            ".java": "java",
        }
        return mapping.get(suffix)

    @staticmethod
    def read_code_file(file_path: str, repo_path: str = "") -> tuple[FileAnalysis, str]:
        rel_path = os.path.relpath(file_path, repo_path) if repo_path else file_path
        ext = os.path.splitext(file_path)[1].lower()

        # 1. Kiểm tra ngôn ngữ hỗ trợ
        if ext not in FileReader.SUPPORTED_LANGUAGES:
            return FileAnalysis(
                path=rel_path,
                language="unknown",
                status="unsupported",
                error=f"Ngôn ngữ với đuôi tệp '{ext}' chưa được hỗ trợ."
            ), ""

        # 2. Kiểm tra file tồn tại
        if not os.path.exists(file_path):
            return FileAnalysis(
                path=rel_path,
                language=FileReader.SUPPORTED_LANGUAGES[ext],
                status="invalid",
                error=f"Không tìm thấy file: {file_path}"
            ), ""

        # 3. Đọc nội dung file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 4. Kiểm tra file rỗng
            if not content.strip():
                return FileAnalysis(
                    path=rel_path,
                    language=FileReader.SUPPORTED_LANGUAGES[ext],
                    status="empty",
                    error="File rỗng, không có nội dung để phân tích."
                ), ""

            return FileAnalysis(
                path=rel_path,
                language=FileReader.SUPPORTED_LANGUAGES[ext],
                status="ok"
            ), content

        except Exception as e:
            return FileAnalysis(
                path=rel_path,
                language=FileReader.SUPPORTED_LANGUAGES[ext],
                status="invalid",
                error=f"Lỗi đọc file: {str(e)}"
            ), ""
