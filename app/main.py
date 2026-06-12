from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from app.config import Monitor, Settings, load_config
from app.db import PriceDatabase
from app.models import PriceSnapshot
from app.notifiers import AlertMessage, MultiNotifier
from app.providers.generic_price_page import GenericPricePageProvider


def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def should_alert(
    monitor: Monitor,
    settings: Settings,
    db: PriceDatabase,
    previous: dict | None,
    snap: PriceSnapshot,
) -> tuple[bool, str]:
    reasons: list[str] = []

    if monitor.alert_when_price_below_max and monitor.max_price_brl is not None:
        if snap.min_price_brl <= monitor.max_price_brl:
            reasons.append(f"preço abaixo do teto de {brl(monitor.max_price_brl)}")

    if previous:
        prev_price = float(previous["min_price_brl"])
        if snap.min_price_brl != prev_price and monitor.alert_on_any_change:
            reasons.append(f"mudou de {brl(prev_price)} para {brl(snap.min_price_brl)}")
        if snap.min_price_brl < prev_price:
            drop_percent = ((prev_price - snap.min_price_brl) / prev_price) * 100
            if drop_percent >= monitor.min_drop_percent:
                reasons.append(f"queda de {drop_percent:.1f}%: {brl(prev_price)} -> {brl(snap.min_price_brl)}")
    else:
        if monitor.max_price_brl is not None and snap.min_price_brl <= monitor.max_price_brl:
            reasons.append("primeira consulta já está dentro do preço desejado")

    if not reasons:
        return False, "sem mudança relevante"

    if not db.can_alert(monitor.name, settings.alert_cooldown_minutes):
        return False, "alerta suprimido pelo cooldown"

    return True, "; ".join(reasons)


def build_alert(monitor: Monitor, snap: PriceSnapshot, reason: str) -> AlertMessage:
    prices_preview = ", ".join(brl(p) for p in snap.all_prices_brl[:10])
    body = f"""Monitor: {monitor.name}
Motivo: {reason}
Menor preço encontrado: {brl(snap.min_price_brl)}
Preços capturados: {prices_preview}
Horário da consulta: {snap.checked_at.astimezone().strftime('%d/%m/%Y %H:%M:%S')}
Página: {snap.page_title or 'sem título'}
URL: {monitor.url}

Observação: confirme disponibilidade e valor final no checkout antes de comprar.
"""
    return AlertMessage(subject=f"✈️ Alerta de passagem: {brl(snap.min_price_brl)}", body=body)


async def check_monitor(
    monitor: Monitor,
    settings: Settings,
    db: PriceDatabase,
    provider: GenericPricePageProvider,
    notifier: MultiNotifier,
) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Consultando: {monitor.name}")
    previous = db.get_previous_snapshot(monitor.name)
    try:
        snap = await provider.fetch(monitor)
        db.insert_snapshot(snap)
        alert, reason = should_alert(monitor, settings, db, previous, snap)
        print(f"  Menor preço: {brl(snap.min_price_brl)} | {reason}")
        if alert:
            notifier.send(build_alert(monitor, snap, reason))
            db.record_alert(monitor.name, snap.min_price_brl, reason)
            print("  Alerta enviado.")
    except Exception as exc:  # noqa: BLE001
        screenshot_path = None
        # O screenshot detalhado é feito dentro do Playwright quando adaptarmos por site.
        # Aqui registramos a falha de forma rastreável.
        db.record_failure(monitor.name, str(exc), screenshot_path)
        print(f"  ERRO: {exc}")


async def run_once(config_path: str) -> None:
    load_dotenv()
    settings, monitors = load_config(config_path)
    enabled = [m for m in monitors if m.enabled]
    if not enabled:
        print("Nenhum monitor habilitado. Edite config.yaml e coloque enabled: true com uma URL válida.")
        return

    db = PriceDatabase()
    notifier = MultiNotifier()
    provider = GenericPricePageProvider(settings)

    for monitor in enabled:
        if monitor.provider != "generic":
            print(f"Provider ainda não suportado: {monitor.provider}. Use provider: generic")
            continue
        await check_monitor(monitor, settings, db, provider, notifier)


async def run_forever(config_path: str) -> None:
    settings, _ = load_config(config_path)
    while True:
        await run_once(config_path)
        await asyncio.sleep(settings.check_interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor de preços de passagens aéreas")
    parser.add_argument("--config", default="config.yaml", help="Caminho do arquivo config.yaml")
    parser.add_argument("--once", action="store_true", help="Executa uma consulta e encerra")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once(args.config))
    else:
        asyncio.run(run_forever(args.config))


if __name__ == "__main__":
    main()
