from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceSnapshot:
    monitor_name: str
    provider: str
    url: str
    checked_at: datetime
    min_price_brl: float
    all_prices_brl: list[float]
    page_title: str | None = None
    raw_excerpt: str | None = None
