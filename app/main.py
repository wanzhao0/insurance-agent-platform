"""HTTP 进程入口。

此文件只负责组装 Web 应用：创建容器、挂中间件、注册路由和托管静态文件。聊天、检索、数据库
等业务逻辑分别位于 application 和 infrastructure，避免 HTTP 层变成业务中心。
"""

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
from app.core.tracing import setup_tracing


settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


class SPAStaticFiles(StaticFiles):
    """为前端路由提供回退页面。

    浏览器直接访问 `/knowledge` 这类前端路由时，服务器实际不存在同名文件；返回 `index.html`
    后由前端路由接管。带扩展名的真实静态文件仍按普通文件处理。
    """

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
    """FastAPI 的启动/停止钩子。

    每个 API 进程拥有一个容器实例；容器负责打开或关闭数据库、向量库、模型客户端等资源。
    路由函数无需自己创建连接，也更方便在测试中替换基础设施实现。
    """
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
setup_tracing(app, settings)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


static_dir = Path(__file__).parent / "static"
frontend_dir = static_dir / "frontend"
app.mount(
    "/prototype",
    StaticFiles(directory=static_dir / "prototype", html=True),
    name="legacy-prototype",
)
frontend_static = SPAStaticFiles(
    directory=frontend_dir if frontend_dir.exists() else static_dir, html=True
)
app.mount("/", frontend_static, name="frontend")
