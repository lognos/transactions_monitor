"""Error shape from docs/contracts.md §4: {"error": {"code", "message"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.server.serialization import public_data
from app.server.observability import record_server_error


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict[str, Any] | None = None):
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        body = {"error": {"code": exc.code, "message": exc.message}, **exc.extra}
        return JSONResponse(public_data(body), status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            {"error": {"code": code, "message": str(exc.detail)}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        if any(cls.__name__ == "ModelUnavailableError" for cls in type(exc).__mro__):
            return JSONResponse(
                {"error": {"code": "model_unavailable", "message":
                    "The model is unavailable or over its quota. No evaluation was saved."}},
                status_code=503,
            )
        error_id = record_server_error(request, exc)
        rate_limited = any(cls.__name__ == "ModelRateLimitError" for cls in type(exc).__mro__)
        message = (
            "The model provider's request limit was reached. Check its quota or wait for the limit to reset."
            if rate_limited else "The request could not be completed."
        )
        return JSONResponse(
            {"error": {"code": "internal_error", "message": f"{message} Reference: {error_id}"}},
            status_code=500,
            headers={"X-Error-Id": error_id},
        )

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
