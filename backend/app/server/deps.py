"""Identity: every request names its principal in X-Principal-Id."""

from typing import Any

from fastapi import Header

from app.db import get_db
from app.server.errors import ApiError


async def current_principal(x_principal_id: str | None = Header(default=None)) -> dict[str, Any]:
    if not x_principal_id:
        raise ApiError(401, "unknown_principal", "Missing X-Principal-Id header")
    principal = await get_db().principals.find_one({"_id": x_principal_id})
    if principal is None:
        raise ApiError(401, "unknown_principal", f"Unknown principal '{x_principal_id}'")
    return principal
