import os
from contextlib import asynccontextmanager

os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
