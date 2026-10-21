"""Aviso diario: lo lanza GitHub Actions (gratis) a las 20:35 hora de Madrid."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from . import config as cfg_mod
from .bot import _fmt_hours
from .config import TZ
from .prices import fetch_prices


def main():
    now = datetime.now(ZoneInfo(TZ))
    if now.hour != 20 and not os.getenv("FORCE"):  # el cron corre en UTC con 2 horarios (verano/invierno)
        return
    cfg = cfg_mod.load()
    prices = fetch_prices(cfg.esios_token, now.date() + timedelta(days=1), days=1)
    if not prices:
        return
    cheap = sorted(h for h, _ in sorted(prices.items(), key=lambda x: x[1])[:6])
    avg = sum(prices.values()) / len(prices)
    text = f"⚡ Precio de mañana: media {avg:.3f} €/kWh.\n🕒 Mejores horas para cargar:\n{_fmt_hours(cheap, now)}"
    httpx.post(f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
               json={"chat_id": cfg.chat_id, "text": text}, timeout=20).raise_for_status()


if __name__ == "__main__":
    main()
