# app/main.py
@app.post("/api/v1/analyze-repo", response_model=RepoAnalysisResponse)
async def analyze_repository(request: RepoAnalysisRequest):
    if not request.files:
        raise HTTPException(status_code=422, detail="Danh sách files phân tích không được để rỗng.")

    analyzed_files = []
    for file_input in request.files:
        lang = file_input.language or FileReader.detect_language(file_input.path)

        try:
            if not file_input.content.strip():
                analyzed_files.append(FileAnalysis(path=file_input.path, language=lang, status="empty"))
                continue

            if lang not in ("python", "java"):
                analyzed_files.append(FileAnalysis(path=file_input.path, language=lang, status="unsupported",
                                                  error=f"Ngôn ngữ '{lang}' chưa hỗ trợ"))
                continue

            tree, error = ASTAnalyzer.parse_code(file_input.content, lang)
            if error:
                analyzed_files.append(FileAnalysis(path=file_input.path, language=lang, status="invalid", error=error))
                continue

            if lang == "python":
                classes, functions, endpoints = EntityExtractor.extract_python_entities(tree, file_input.content)
            else:
                classes, functions, endpoints = EntityExtractor.extract_java_entities(tree, file_input.content)

            analyzed_files.append(FileAnalysis(
                path=file_input.path,
                language=lang,
                status="ok",
                classes=classes,
                functions=functions,
                endpoints=endpoints
            ))
        except Exception as exc:
            analyzed_files.append(FileAnalysis(
                path=file_input.path,
                language=lang,
                status="invalid",
                error=f"Analyzer crashed: {exc.__class__.__name__}: {exc}"
            ))

    return RepoAnalysisResponse(scope=request.scope, target=request.target, files=analyzed_files)
@app.get("/health")
async def health():
    return {"status": "ok"}