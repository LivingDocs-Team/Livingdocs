import os
from pathlib import Path
from app.models import FileAnalysis

class FileReader:
    SUPPORTED_LANGUAGES = {
        ".py": "python",
        ".java": "java",
    }
    @staticmethod
    def detect_language(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()

        languages = {
            **FileReader.SUPPORTED_LANGUAGES,
            ".rb": "ruby",
        }

        return languages.get(ext, "unknown")

    @staticmethod
    def detect_language(path: str):
        suffix = Path(path).suffix.lower()
        return FileReader.SUPPORTED_LANGUAGES.get(suffix)

    @staticmethod
    def read_code_file(file_path: str, repo_path: str = "") -> tuple[FileAnalysis, str]:
        rel_path = os.path.relpath(file_path, repo_path) if repo_path else file_path
        ext = os.path.splitext(file_path)[1].lower()

        if ext not in FileReader.SUPPORTED_LANGUAGES:
            return FileAnalysis(
                path=rel_path,
                language="unknown",
                status="unsupported",
                error=f"Ngôn ngữ với đuôi tệp '{ext}' chưa được hỗ trợ."
            ), ""

        if not os.path.exists(file_path):
            return FileAnalysis(
                path=rel_path,
                language=FileReader.SUPPORTED_LANGUAGES[ext],
                status="invalid",
                error=f"Không tìm thấy file: {file_path}"
            ), ""

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

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