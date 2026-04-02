import re
from pathlib import Path

def refactor_app_py():
    app_py_path = Path("src/dashboard/app.py")
    content = app_py_path.read_text("utf-8")
    if "AuthMiddleware" not in content:
        insert_code = """
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse
from src.auth import verify_session_token, COOKIE_NAME

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
"""
        content = content.replace("app = FastAPI(title=\"Outreach Agent Dashboard\")", "app = FastAPI(title=\"Outreach Agent Dashboard\")\n" + insert_code)
        app_py_path.write_text(content, "utf-8")
        print("Refactored app.py")

def refactor_routes_py():
    routes_py_path = Path("src/dashboard/routes.py")
    content = routes_py_path.read_text("utf-8")
    
    # Inject user = get_current_user(request) before session = get_session() 
    # if it's inside a route function (has 'request' or something).
    # Since we can't reliably parse AST here, a simple regex on standard indentation:
    content = re.sub(
        r"(\s+)session = get_session\(\)",
        r"\1user = get_current_user(request) if 'request' in locals() else None\n\1session = get_session()",
        content
    )
    
    # Models to filter
    models = ["JobShortlist", "PeopleMapper", "OutreachLog", "ResponseTracker", "CVVersion", "ApplicationMemory"]
    
    filter_injection = "user.id if user else 1"  # Fallback to user 1 for background tasks or missing context
    
    for M in models:
        # If it has an existing filter: `.filter(` -> `.filter(M.user_id == user.id, `
        content = re.sub(
            rf"session\.query\({M}\)\.filter\(",
            f"session.query({M}).filter({M}.user_id == ({filter_injection}), ",
            content
        )
        
        # If it has .order_by or .all() immediately after query
        content = re.sub(
            rf"session\.query\({M}\)\.(order_by|all|limit|group_by)\(",
            f"session.query({M}).filter({M}.user_id == ({filter_injection})).\\1(",
            content
        )
        
        # Aggregate queries
        content = re.sub(
            rf"session\.query\((func\.count\({M}\.id\)|{M}\.status\,\s*func\.count\({M}\.id\)|func\.count\({M}\.id\))\)\.filter\(",
            f"session.query(\\1).filter({M}.user_id == ({filter_injection}), ",
            content
        )
        content = re.sub(
            rf"session\.query\((func\.count\({M}\.id\))\)\.(scalar|all)\(",
            f"session.query(\\1).filter({M}.user_id == ({filter_injection})).\\2(",
            content
        )

        # session.get(...) to filter_by
        content = re.sub(
            rf"session\.get\({M},\s*([a-zA-Z0-9_\.\(\)]+)\)",
            f"session.query({M}).filter({M}.id == \\1, {M}.user_id == ({filter_injection})).first()",
            content
        )

    # Some functions like update_job_status take `job_id` but not `request`. 
    # The `if 'request' in locals() else None` handles exceptions, but for multi-tenant 
    # safety we must add request to their signature if they are routes!
    # Let's dynamically add `request: Request` to routes missing it.
    
    content = re.sub(
        r"(@router\.post\(\"/jobs/\{job_id\}/status\"\)\n)def update_job_status\(",
        r"\1def update_job_status(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/jobs/\{job_id\}/apply\"\)\n)def apply_to_job\(",
        r"\1def apply_to_job(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/outreach/\{outreach_id\}/approve\"\)\n)def approve_outreach\(",
        r"\1def approve_outreach(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/outreach/\{outreach_id\}/send\"\)\n)def send_outreach\(",
        r"\1def send_outreach(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/outreach/approve-all\"\)\n)def approve_all_drafts\(",
        r"\1def approve_all_drafts(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.get\(\"/cvs/download/\{cv_id\}\"\)\n)def download_cv\(",
        r"\1def download_cv(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/cvs/generate/\{job_id\}\"\)\n)def generate_cv\(",
        r"\1def generate_cv(request: Request, ",
        content
    )
    content = re.sub(
        r"(@router\.post\(\"/api/notifications/\{notif_id\}/dismiss\"\)\n)def api_dismiss_notification\(",
        r"\1def api_dismiss_notification(request: Request, ",
        content
    )

    routes_py_path.write_text(content, "utf-8")
    print("Refactored routes.py thoroughly")

if __name__ == "__main__":
    refactor_app_py()
    refactor_routes_py()
