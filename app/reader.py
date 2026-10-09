import os

class FileReader:
    @staticmethod
    def read_code_file(file_path: str) -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Không tìm thấy tệp mã nguồn: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
