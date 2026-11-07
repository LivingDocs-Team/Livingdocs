import os
from app.models import FileAnalysis

class FileReader:
    SUPPORTED_LANGUAGES = {
        ".py": "python",
        ".java": "java"
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

    @staticmethod
    def read_inline_content(path: str, content: str, language: str = None) -> tuple[FileAnalysis, str]:
        """LD-395: giống read_code_file nhưng nhận nội dung có sẵn (Analyzer không có repo trên đĩa).

        Trả về (FileAnalysis, mã nguồn đã bỏ BOM). Chuẩn hóa ngôn ngữ (ERR-BE-05) và bỏ BOM (ERR-BE-04).
        """
        ext = os.path.splitext(path)[1].lower()
        declared = language.strip().lower() if isinstance(language, str) and language.strip() else None
        supported = set(FileReader.SUPPORTED_LANGUAGES.values())

        if declared in supported:
            lang = declared
        else:
            lang = FileReader.SUPPORTED_LANGUAGES.get(ext)

        if lang is None:
            return FileAnalysis(
                path=path,
                language=declared or "unknown",
                status="unsupported",
                error=f"Ngôn ngữ với đuôi tệp '{ext}' chưa được hỗ trợ."
            ), ""

        clean = (content or "").lstrip("\ufeff")
        if not clean.strip():
            return FileAnalysis(
                path=path,
                language=lang,
                status="empty",
                error="File rỗng, không có nội dung để phân tích."
            ), ""

        return FileAnalysis(path=path, language=lang, status="ok"), clean
