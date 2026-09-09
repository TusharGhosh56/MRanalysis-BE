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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def debug_middleware(request: Request, call_next):
        if "debug" in request.url.path:
            return JSONResponse({
                "url": str(request.url),
                "path": request.url.path,
                "scope_path": request.scope.get("path"),
                "scope_root_path": request.scope.get("root_path"),
                "scope_raw_path": str(request.scope.get("raw_path")),
                "headers": dict(request.headers),
            })
        return await call_next(request)


    @app.get("/", tags=["health"])
    @app.get("/api", tags=["health"])
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

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
