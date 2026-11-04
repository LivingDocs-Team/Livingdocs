from fastapi import FastAPI
import uvicorn

app = FastAPI(title="AI Service Mock for CI Port 8001")

@app.get("/")
async def root():
    return {"status": "ok", "generator": "online"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/generate")
async def generate_docs(payload: dict):
    # Giả lập phản hồi 202 Accepted cho AI Service Integration Test
    return {"status": "accepted", "job_id": "mock-job-123"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
