from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class Settings:
    check_interval_minutes: int = 30
    headless: bool = True
    browser_timeout_seconds: int = 45
    alert_cooldown_minutes: int = 120
    user_agent: str | None = None
    screenshot_on_error: bool = True
    notify_on_recovery: bool = True


@dataclass(frozen=True)
class Monitor:
    name: str
    provider: str
    enabled: bool
    url: str
    max_price_brl: float | None = None
    min_drop_percent: float = 3.0
    alert_on_any_change: bool = False
    alert_when_price_below_max: bool = True
    notes: str | None = None


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "y"}


def load_config(path: str | Path = "config.yaml") -> tuple[Settings, list[Monitor]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo {path} não encontrado. Copie config.example.yaml para config.yaml e edite as URLs."
        )

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_settings = data.get("settings", {}) or {}
    settings = Settings(
        check_interval_minutes=int(raw_settings.get("check_interval_minutes", 30)),
        headless=_as_bool(raw_settings.get("headless"), True),
        browser_timeout_seconds=int(raw_settings.get("browser_timeout_seconds", 45)),
        alert_cooldown_minutes=int(raw_settings.get("alert_cooldown_minutes", 120)),
        user_agent=raw_settings.get("user_agent"),
        screenshot_on_error=_as_bool(raw_settings.get("screenshot_on_error"), True),
        notify_on_recovery=_as_bool(raw_settings.get("notify_on_recovery"), True),
    )

    monitors: list[Monitor] = []
    for item in data.get("monitors", []) or []:
        url = str(item.get("url", "")).strip()
        if not url or url.startswith("COLE_AQUI"):
            # Mantém no config, mas não roda. Ajuda no primeiro setup.
            enabled = False
        else:
            enabled = _as_bool(item.get("enabled"), True)

        monitors.append(
            Monitor(
                name=str(item["name"]),
                provider=str(item.get("provider", "generic")).lower(),
                enabled=enabled,
                url=url,
                max_price_brl=float(item["max_price_brl"]) if item.get("max_price_brl") is not None else None,
                min_drop_percent=float(item.get("min_drop_percent", 3.0)),
                alert_on_any_change=_as_bool(item.get("alert_on_any_change"), False),
                alert_when_price_below_max=_as_bool(item.get("alert_when_price_below_max"), True),
                notes=item.get("notes"),
            )
        )

    return settings, monitors
