"""Utilidades compartidas por los módulos."""

from __future__ import annotations

import json
from typing import Any


def to_json(data: Any, *, indent: int | None = 2) -> str:
    """Serializa a JSON legible, tolerando valores no serializables."""
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)


def clamp(value: float, low: float, high: float) -> float:
    """Limita ``value`` al rango [low, high]."""
    return max(low, min(high, value))
