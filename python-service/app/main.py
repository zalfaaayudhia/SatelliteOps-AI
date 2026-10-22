from fastapi import FastAPI

app = FastAPI(
    title="SatelliteOps AI",
    description="AI-powered satellite operations assistant",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "python-ai",
    }
