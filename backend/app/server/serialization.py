"""Keep MongoDB internals out of HTTP responses, including agent results."""

from datetime import date, datetime, timezone
from typing import Any


def public_data(value: Any) -> Any:
    if isinstance(value, dict):
        data = {key: public_data(item) for key, item in value.items() if key != "_id"}
        # Older evaluations retain their original results; supply the new view
        # fields in responses only, without migrating or changing stored data.
        if "criterion_id" in data and "result" in data:
            data.setdefault("effective_result", data["result"])
            data.setdefault("override", None)
        if "checks" in data and "recommendation" in data:
            data.setdefault("effective_recommendation", data["recommendation"])
        return data
    if isinstance(value, (list, tuple)):
        return [public_data(item) for item in value]
    if isinstance(value, datetime):
        # PyMongo returns naive UTC datetimes unless tz_aware is configured.
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value
