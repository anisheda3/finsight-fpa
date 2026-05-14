"""JSON serialization helpers (date / UUID / Decimal aware)."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


class FinJSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, Decimal):
            return float(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return super().default(o)


def to_json(obj: Any) -> str:
    return json.dumps(obj, cls=FinJSONEncoder)
