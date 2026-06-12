from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import Monitor, Settings
from app.models import PriceSnapshot


# Captura preços com centavos e sem centavos:
# R$ 967
# R$ 2.335
# R$ 2.335,00
# BRL 967
PRICE_REGEXES = [
    re.compile(r"R\$\s*(-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?)"),
    re.compile(r"BRL\s*(-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?)", re.IGNORECASE),
]

COOKIE_BUTTON_TEXTS = [
    "aceitar", "aceito", "accept", "concordo", "continuar", "ok", "entendi",
    "recusar", "não obrigado", "nao obrigado"
]

# Palavras próximas ao preço que indicam que NÃO é preço da passagem.
# Exemplo: economia de R$ 158, taxas R$ 401, desconto -R$ 315.
EXCLUSION_CONTEXT_WORDS = [
    "economia",
    "economize",
    "desconto",
    "taxa",
    "taxas",
    "cupom",
    "saldo",
    "cashback",
]


def parse_brl_price(value: str) -> float:
    clean = value.replace(".", "").replace(",", ".").replace("-", "").strip()
    return round(float(clean), 2)


def _looks_like_auxiliary_value(text: str, start_index: int, matched_value: str) -> bool:
    if matched_value.strip().startswith("-"):
        return True

    before = text[max(0, start_index - 80):start_index].lower()
    return any(word in before for word in EXCLUSION_CONTEXT_WORDS)


def extract_prices_from_text(text: str) -> list[float]:
    prices: list[float] = []

    for regex in PRICE_REGEXES:
        for match in regex.finditer(text):
            value = match.group(1)

            if _looks_like_auxiliary_value(text, match.start(), value):
                continue

            try:
                price = parse_brl_price(value)

                # Filtro defensivo:
                # abaixo de 250 normalmente é taxa/desconto/economia, não passagem.
                # acima de 50000 é valor irreal para nosso uso.
                if 250 <= price <= 50000:
                    prices.append(price)
            except ValueError:
                continue

    return sorted(set(prices))


async def _try_accept_cookies(page) -> None:  # type: ignore[no-untyped-def]
    for text in COOKIE_BUTTON_TEXTS:
        try:
            locator = page.get_by_role("button", name=re.compile(text, re.IGNORECASE))
            if await locator.count() > 0:
                await locator.first.click(timeout=1500)
                return
        except Exception:
            continue


class GenericPricePageProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        Path("screenshots").mkdir(exist_ok=True)

    @retry(
        retry=retry_if_exception_type((RuntimeError, PlaywrightTimeoutError)),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch(self, monitor: Monitor) -> PriceSnapshot:
        timeout_ms = self.settings.browser_timeout_seconds * 1000

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.settings.headless)
            context_kwargs = {
                "locale": "pt-BR",
                "timezone_id": "America/Sao_Paulo",
                "viewport": {"width": 1366, "height": 900},
            }

            if self.settings.user_agent:
                context_kwargs["user_agent"] = self.settings.user_agent

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                await page.goto(monitor.url, wait_until="domcontentloaded", timeout=timeout_ms)
                await _try_accept_cookies(page)

                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    pass

                # Dá mais tempo para sites como 123Milhas carregarem os preços.
                await page.wait_for_timeout(9000)

                text = await page.locator("body").inner_text(timeout=timeout_ms)
                title = await page.title()
                prices = extract_prices_from_text(text)

                if not prices:
                    if self.settings.screenshot_on_error:
                        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", monitor.name)[:80]
                        await page.screenshot(path=f"screenshots/{safe_name}.png", full_page=True)

                    raise RuntimeError(
                        "Nenhum preço em R$ foi encontrado na página. "
                        "Talvez o site exija interação, captcha, login ou tenha mudado o layout."
                    )

                return PriceSnapshot(
                    monitor_name=monitor.name,
                    provider=monitor.provider,
                    url=monitor.url,
                    checked_at=datetime.now(timezone.utc),
                    min_price_brl=min(prices),
                    all_prices_brl=prices[:50],
                    page_title=title,
                    raw_excerpt=text[:1200],
                )

            finally:
                await context.close()
                await browser.close()
