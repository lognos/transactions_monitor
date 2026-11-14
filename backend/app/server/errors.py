"""Error shape from docs/contracts.md §4: {"error": {"code", "message"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict[str, Any] | None = None):
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = {"error": {"code": exc.code, "message": exc.message}, **exc.extra}
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(str(e.get("msg", "")) for e in exc.errors())
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": message}}, status_code=422
        )

    @app.exception_handler(NotImplementedError)
    async def not_built_yet(_: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "not_implemented", "message": f"Not built yet: {exc}"}},
            status_code=501,
        )
