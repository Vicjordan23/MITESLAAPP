"""Aviso diario (20:35 Madrid, lo lanza GitHub Actions): resumen de mañana, alertas y replanificación."""
import os
from datetime import datetime, timedelta

import httpx

from . import config as cfg_mod
from . import core, store
from .planner import plan_charge
from .prices import fetch_prices


def send(cfg, text: str) -> None:
    httpx.post(f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
               json={"chat_id": cfg.chat_id, "text": text}, timeout=20).raise_for_status()


def main():
    now = core.now()
    if now.hour != 20 and not os.getenv("FORCE"):  # el cron corre en UTC con 2 horarios (verano/invierno)
        return
    cfg, data = core.load_all(cfg_mod.load())
    prices = fetch_prices(cfg.esios_token, now.date() + timedelta(days=1), days=1)
    if not prices:
        return
    avg = sum(prices.values()) / len(prices)
    cheap = sorted(h for h, _ in sorted(prices.items(), key=lambda x: x[1])[:6])
    lines = [f"⚡ Precio de mañana: media {avg:.3f} €/kWh (sin impuestos).",
             f"🕒 Mejores horas para cargar:\n{core.fmt_hours(cheap, now)}"]
    if cfg.alerts:
        if avg <= cfg.alert_low:
            lines.insert(0, "🟢 ¡Mañana es un día BARATO! Buen momento para cargar a tope.")
        elif avg >= cfg.alert_high:
            lines.insert(0, "🔴 Mañana la luz está CARA: carga solo lo imprescindible, y en las horas de arriba.")
    plan = data.get("plan")
    if plan and plan.get("prov"):  # se programó antes de conocer los precios de mañana
        all_prices = fetch_prices(cfg.esios_token, now.date(), days=2)
        p = plan_charge(all_prices, now, datetime.fromisoformat(plan["dl"]), plan["cur"], plan["tgt"],
                        cfg.battery_kwh, cfg.car_kw, cfg.efficiency)
        if p.covered:
            rec = core.plan_record(p, plan["cur"], plan["tgt"], datetime.fromisoformat(plan["dl"]))
            data["plan"] = rec
            core.add_history(data, rec)
            store.save(cfg.telegram_token, cfg.chat_id, data)
            lines.append(f"\n📌 He actualizado tu carga programada con los precios definitivos:\n"
                         f"{core.fmt_hours(sorted(core.plan_hours(rec)), now)}\nCoste ≈ {rec['cost']:.2f} €")
    send(cfg, "\n".join(lines))


if __name__ == "__main__":
    main()
