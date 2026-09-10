import os
from contextlib import asynccontextmanager

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import get_settings
from app.workers.tasks import shutdown_executor

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    shutdown_executor(wait=False)



def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    cors_origins = list(settings.CORS_ORIGINS)
    if not any(origin in ("*", "https://*") for origin in cors_origins):
        cors_origins.extend(["*", "https://mr-analysis-kohl.vercel.app"])

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


    @app.get("/", tags=["health"])
    @app.get("/api", tags=["health"])
    @app.api_route("/api/index.py", methods=["GET", "POST", "HEAD"], tags=["health"])
    def root() -> dict[str, str]:
        return {
            "status": "ok",
            "name": settings.APP_NAME,
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["health"])
    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/docs", include_in_schema=False)
    def api_docs():
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/docs")

    # Support /api/v1 (standard), /api, and root prefix so frontends
    # calling either /api/v1/auth/register or /auth/register work seamlessly.
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(api_router, prefix="/api")
    app.include_router(api_router)

    return app


app = create_app()
