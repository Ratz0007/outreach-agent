"""Vercel serverless entry point — with error diagnostics."""
import sys
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.dashboard.app import app as _app
    from fastapi import Request
    from fastapi.responses import PlainTextResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    class ErrorCatchMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            try:
                response = await call_next(request)
                return response
            except Exception as e:
                tb = traceback.format_exc()
                return PlainTextResponse(
                    f"Runtime error:\n\n{tb}",
                    status_code=500,
                )

    _app.add_middleware(ErrorCatchMiddleware)
    app = _app

except Exception as e:
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    app = FastAPI()
    error_detail = traceback.format_exc()

    @app.get("/{path:path}")
    async def diagnostic(path: str = ""):
        return PlainTextResponse(
            f"Import failed. Debug info:\n\n{error_detail}",
            status_code=500,
        )
