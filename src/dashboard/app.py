"""FastAPI dashboard app — Stage 13.

Dark theme, Tailwind CDN, vanilla JS. Clean and functional.
http://localhost:8000
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from src.db.session import init_db
from starlette.middleware.base import BaseHTTPMiddleware

from fastapi.middleware.cors import CORSMiddleware
from src.auth import verify_session_token, COOKIE_NAME

app = FastAPI(title="Outreach Agent Dashboard")

# ── CORS Middleware ──────────────────────────────────────────────
# Needed to allow Next.js (port 3000) to communicate with FastAPI (port 8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for public SaaS, restrict later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow open routes
        open_paths = ["/login", "/register", "/static", "/api/actions", "/api/health"]
        if any(request.url.path.startswith(p) for p in open_paths):
            return await call_next(request)
        
        # Check auth
        token = request.cookies.get(COOKIE_NAME)
        if not token or not verify_session_token(token):
            return RedirectResponse(url="/login", status_code=303)
            
        return await call_next(request)

app.add_middleware(AuthMiddleware)


TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.on_event("startup")
def startup():
    init_db()


# ── Import routes ─────────────────────────────────────────────────
from src.dashboard.routes import router, api_router  # noqa: E402
app.include_router(router)
app.include_router(api_router)
