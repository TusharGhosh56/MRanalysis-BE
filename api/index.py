import os
import sys

# Silence GitPython missing system git binary error on serverless runtimes
os.environ["GIT_PYTHON_REFRESH"] = "quiet"

# Ensure the project root directory is on sys.path for serverless runtimes
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.main import app as fastapi_app  # noqa: E402


class VercelPathFixMiddleware:
    """Restores the original request path when Vercel rewrites requests to /api/index.py."""

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            headers = dict(scope.get("headers", []))
            matched_path = (
                headers.get(b"x-matched-path")
                or headers.get(b"x-invoke-path")
                or headers.get(b"x-forwarded-uri")
            )
            if matched_path:
                original_path = matched_path.decode("utf-8", errors="ignore").split("?")[0]
                if scope.get("path") in ("/api/index.py", "/api/index", "/api/index.py/"):
                    scope["path"] = original_path
        await self.asgi_app(scope, receive, send)


app = VercelPathFixMiddleware(fastapi_app)



