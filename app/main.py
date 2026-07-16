from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.bootstrap.container import build_container
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware


settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the Vue entry point for client-side routes on direct navigation."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or scope["method"] not in {"GET", "HEAD"}:
                raise
            if Path(path).name.count("."):
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = build_container(settings)
    app.state.container = container
    await container.startup()
    logger.info(
        "application_started",
        extra={"environment": settings.environment, "model_provider": settings.model_provider},
    )
    yield
    await container.shutdown()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A configurable customer service Agent platform with knowledge-base retrieval.",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)

static_dir = Path(__file__).parent / "static"
frontend_dir = static_dir / "frontend"
app.mount("/prototype", StaticFiles(directory=static_dir / "prototype", html=True), name="legacy-prototype")
frontend_static = SPAStaticFiles(directory=frontend_dir if frontend_dir.exists() else static_dir, html=True)
app.mount("/", frontend_static, name="frontend")
