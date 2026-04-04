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

app = FastAPI(
    title="Outreach Agent Dashboard",
    redirect_slashes=False  # Crucial for CORS preflight (no 307 redirects on /api/ endpoints)
)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1. Skip auth check for preflight OPTIONS requests (required for CORS)
        if request.method == "OPTIONS":
            return await call_next(request)
            
        # 2. Allow open routes
        open_paths = ["/login", "/register", "/static", "/api/actions", "/api/health", "/api/auth/google"]
        if any(request.url.path.startswith(p) for p in open_paths):
            return await call_next(request)
        
        # 3. Check auth
        token = request.cookies.get(COOKIE_NAME)
        if not token or not verify_session_token(token):
            # 4. If an API request fails auth, return 401 instead of a redirect
            if request.url.path.startswith("/api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": "Unauthorized", "detail": "Invalid or missing session token"}, status_code=401)
            
            # 5. Only redirect UI (HTML) routes to /login
            return RedirectResponse(url="/login", status_code=303)
            
        return await call_next(request)

app.add_middleware(AuthMiddleware)

# ── CORS Middleware (Must be added AFTER AuthMiddleware to run FIRST) ────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://outreach-agent-app.vercel.app",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["set-cookie"],
)


TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


@app.on_event("startup")
def startup():
    init_db()


# ── Import routes ─────────────────────────────────────────────────
from src.dashboard.routes import router, api_router  # noqa: E402
app.include_router(router)
app.include_router(api_router)
