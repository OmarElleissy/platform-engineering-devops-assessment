"""FastAPI application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Platform Engineering Assessment")


@app.get("/health")
async def health() -> dict[str, str]:
    """Report whether the application process is healthy."""
    return {"status": "healthy"}
