from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple


PresenceConditions = List[str]
PcCacheKey = Tuple[str, str, str]


@dataclass(frozen=True)
class ExtractionRequest:
    idx: int
    project: str
    file_field: str
    caller: str
    callee: str
