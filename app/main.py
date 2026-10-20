from typing import List
from fastapi import FastAPI
from pydantic import BaseModel
from app.models import FileAnalysis
from app.reader import FileReader
from app.analyzer import ASTAnalyzer
from app.extractor import EntityExtractor

app = FastAPI(title="LivingDocs - Source Code Analysis Service (LD-328)")
@app.get("/health")
def health():
    return {"status": "ok"}

class AnalysisRequest(BaseModel):
    scope: str = "file"  # file | module | repository
    target: str
    file_paths: List[str]

class AnalysisResponse(BaseModel):
    scope: str
    target: str
    files: List[FileAnalysis]

@app.post("/api/v1/analyze-repo", response_model=AnalysisResponse)
def analyze_repository(req: AnalysisRequest):
    analyzed_files = []

    for path in req.file_paths:
        file_info, content = FileReader.read_code_file(path)

        # Nếu file bị lỗi đọc / rỗng / không hỗ trợ -> giữ nguyên status & error
        if file_info.status != "ok":
            analyzed_files.append(file_info)
            continue

        # Phân tích Python
        if file_info.language == "python":
            tree, err = ASTAnalyzer.parse_python_ast(content)
            if err:
                file_info.status = "invalid"
                file_info.error = err
            else:
                classes, funcs, endpoints = EntityExtractor.extract_python_entities(tree, content)
                file_info.classes = classes
                file_info.functions = funcs
                file_info.endpoints = endpoints

        # Phân tích Java
        elif file_info.language == "java":
            tree, err = ASTAnalyzer.parse_java_ast(content)
            if err:
                file_info.status = "invalid"
                file_info.error = err
            else:
                classes, funcs, endpoints = EntityExtractor.extract_java_entities(tree, content)
                file_info.classes = classes
                file_info.functions = funcs
                file_info.endpoints = endpoints

        analyzed_files.append(file_info)

    return AnalysisResponse(
        scope=req.scope,
        target=req.target,
        files=analyzed_files
    )
