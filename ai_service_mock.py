from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Mock AI Service")

@app.get("/")
async def root():
    return {"status": "ok", "generator": "online"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
