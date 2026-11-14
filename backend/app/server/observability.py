"""Optional server telemetry. Credentials stay in the process environment."""

import logging
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request

from app.config import settings

logger = logging.getLogger(__name__)


def configure_observability(app: FastAPI) -> None:
    app.state.logfire_enabled = False
    token = os.getenv("LOGFIRE_WRITE_TOKEN") or os.getenv("LOGFIRE_TOKEN")
    if not token:
        return
    try:
        import logfire

        logfire.configure(
            token=token,
            service_name="auditflow-api",
            service_version="0.1.0",
            environment=os.getenv("LOGFIRE_ENVIRONMENT", "development"),
            console=False,
            inspect_arguments=False,
        )
        logfire.instrument_fastapi(
            app, capture_headers=False,
            # FastAPI's default mapper includes parsed bodies and principals.
            # Capture route identifiers, never chat text or transaction payloads.
            request_attributes_mapper=lambda request, attributes: {
                key: value for key, value in request.path_params.items()
                if key in {"eval_id", "txn_id", "criterion_id"}
            },
        )
        logfire.instrument_httpx(
            capture_headers=False, capture_request_body=False, capture_response_body=False,
        )
        app.state.logfire_enabled = True
        logfire.info("AuditFlow server telemetry enabled", llm_model=settings.llm_model)
    except Exception as exc:
        # Observability should not prevent the demo server from starting.
        logger.error("Logfire setup unavailable (%s)", type(exc).__name__)


def record_server_error(request: Request, exc: Exception) -> str:
    error_id = uuid4().hex[:12]
    route = getattr(request.scope.get("route"), "path", request.url.path)
    attributes: dict[str, Any] = {
        "error_id": error_id, "method": request.method, "route": route,
        **request.path_params,
    }
    if getattr(request.app.state, "logfire_enabled", False):
        import logfire

        logfire.exception("Request failed {error_id}: {method} {route}", _exc_info=exc, **attributes)
    else:
        logger.error(
            "Request failed %s: %s %s", error_id, request.method, route,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    return error_id
