from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.core.request_context import get_request_id


class AgentError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgentError)
    async def handle_agent_error(_: Request, exc: AgentError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}, "request_id": get_request_id()},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "request validation failed",
                    "details": exc.errors(),
                },
                "request_id": get_request_id(),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        get_logger("app.errors").exception("unexpected_error", extra={"request_id": get_request_id()})
        return JSONResponse(
            status_code=500,
            content={
                "error": {"code": "internal_error", "message": "internal server error"},
                "request_id": get_request_id(),
            },
        )
