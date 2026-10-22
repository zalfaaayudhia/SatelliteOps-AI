
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="SatelliteOps AI",
    description="AI-powered satellite operations assistant",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "python-ai",
    }


@app.post("/analyze")
def analyze(request: AnalyzeRequest):
    return {
        "status": "success",
        "service": "python-ai",
        "received_message": request.message,
        "analysis": f"Python AI service received: {request.message}",
    }
