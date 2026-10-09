from fastapi import FastAPI
from pydantic import BaseModel
from app.analyzer import ASTAnalyzer
from app.extractor import EntityExtractor
from app.dependency import DependencyAnalyzer

# Khởi tạo ứng dụng FastAPI cho AI Service
app = FastAPI(
    title="LivingDocs - Source Code Analysis Service",
    description="Dịch vụ AI phân tích mã nguồn cho dự án LivingDocs",
    version="1.0.0"
)

class CodeRequest(BaseModel):
    code: str
    language: str

@app.get("/")
def home():
    return {"message": "Source Code Analysis Service is running!"}

@app.post("/api/v1/analyze")
def analyze_code(req: CodeRequest):
    lang = req.language.lower()
    
    # Xử lý nếu mã nguồn là Python
    if lang == "python":
        tree = ASTAnalyzer.parse_python_ast(req.code)
        entities = EntityExtractor.extract_python_entities(tree)
        dependencies = DependencyAnalyzer.get_python_imports(tree)
        return {
            "status": "success", 
            "language": "python", 
            "entities": entities, 
            "dependencies": dependencies
        }
    
    # Xử lý nếu mã nguồn là Java
    elif lang == "java":
        tree = ASTAnalyzer.parse_java_ast(req.code)
        entities = EntityExtractor.extract_java_entities(tree)
        dependencies = DependencyAnalyzer.get_java_imports(tree)
        return {
            "status": "success", 
            "language": "java", 
            "entities": entities, 
            "dependencies": dependencies
        }

    return {"status": "error", "message": f"Ngôn ngữ '{req.language}' chưa được hỗ trợ."}
