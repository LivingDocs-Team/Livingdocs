from fastapi import FastAPI
from pydantic import BaseModel
from app.analyzer import ASTAnalyzer
from app.extractor import EntityExtractor
from app.dependency import DependencyAnalyzer

app = FastAPI(title="LivingDocs - Source Code Analysis Service")

class CodeRequest(BaseModel):
    code: str
    language: str

@app.post("/api/v1/analyze")
def analyze_code(req: CodeRequest):
    lang = req.language.lower()
    if lang == "python":
        tree = ASTAnalyzer.parse_python_ast(req.code)
        entities = EntityExtractor.extract_python_entities(tree)
        dependencies = DependencyAnalyzer.get_python_imports(tree)
        return {"status": "success", "entities": entities, "dependencies": dependencies}

    elif lang == "java":
        tree = ASTAnalyzer.parse_java_ast(req.code)
        entities = EntityExtractor.extract_java_entities(tree)
        dependencies = DependencyAnalyzer.get_java_imports(tree)
        return {"status": "success", "entities": entities, "dependencies": dependencies}

    return {"status": "error", "message": "Unsupported language"}
