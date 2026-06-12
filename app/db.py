from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.models import PriceSnapshot


class PriceDatabase:
    def __init__(self, path: str | Path = "data/flight_prices.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS price_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    url TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    min_price_brl REAL NOT NULL,
                    all_prices_json TEXT NOT NULL,
                    page_title TEXT,
                    raw_excerpt TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_price_checks_monitor_time
                ON price_checks (monitor_name, checked_at DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_name TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    price_brl REAL NOT NULL,
                    reason TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_monitor_time
                ON alerts (monitor_name, sent_at DESC);

                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_name TEXT NOT NULL,
                    failed_at TEXT NOT NULL,
                    error TEXT NOT NULL,
                    screenshot_path TEXT
                );
                """
            )

    def insert_snapshot(self, snap: PriceSnapshot) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO price_checks
                (monitor_name, provider, url, checked_at, min_price_brl, all_prices_json, page_title, raw_excerpt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.monitor_name,
                    snap.provider,
                    snap.url,
                    snap.checked_at.astimezone(timezone.utc).isoformat(),
                    snap.min_price_brl,
                    json.dumps(snap.all_prices_brl, ensure_ascii=False),
                    snap.page_title,
                    snap.raw_excerpt,
                ),
            )

    def get_previous_snapshot(self, monitor_name: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT * FROM price_checks
                WHERE monitor_name = ?
                ORDER BY checked_at DESC
                LIMIT 1
                """,
                (monitor_name,),
            ).fetchone()
            return dict(row) if row else None

    def get_last_alert(self, monitor_name: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute(
                """
                SELECT * FROM alerts
                WHERE monitor_name = ?
                ORDER BY sent_at DESC
                LIMIT 1
                """,
                (monitor_name,),
            ).fetchone()
            return dict(row) if row else None

    def can_alert(self, monitor_name: str, cooldown_minutes: int) -> bool:
        last = self.get_last_alert(monitor_name)
        if not last:
            return True
        sent_at = datetime.fromisoformat(last["sent_at"])
        return datetime.now(timezone.utc) - sent_at >= timedelta(minutes=cooldown_minutes)

    def record_alert(self, monitor_name: str, price_brl: float, reason: str) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO alerts (monitor_name, sent_at, price_brl, reason)
                VALUES (?, ?, ?, ?)
                """,
                (monitor_name, datetime.now(timezone.utc).isoformat(), price_brl, reason),
            )

    def record_failure(self, monitor_name: str, error: str, screenshot_path: str | None = None) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO failures (monitor_name, failed_at, error, screenshot_path)
                VALUES (?, ?, ?, ?)
                """,
                (monitor_name, datetime.now(timezone.utc).isoformat(), error, screenshot_path),
            )
