import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from . import config as cfg_mod
from .config import TZ
from .planner import plan_charge
from .prices import fetch_prices

log = logging.getLogger("teslabot")
cfg = None


def _now() -> datetime:
    return datetime.now(ZoneInfo(TZ))


def _fmt_hours(hours: list[datetime]) -> str:
    """Agrupa horas consecutivas: 02:00-05:00, 14:00-15:00"""
    if not hours:
        return "—"
    runs, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h - prev != timedelta(hours=1):
            runs.append((start, prev)); start = h
        prev = h
    runs.append((start, prev))
    return ", ".join(f"{a:%a %H:%M}-{b + timedelta(hours=1):%H:%M}" for a, b in runs)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 Comandos:\n"
        "/precios — precios PVPC de hoy y mañana\n"
        "/cargar <actual%> <objetivo%> <HH:MM> — cuándo conectar para estar listo a esa hora\n"
        "   ej: /cargar 30 80 07:30"
    )


async def precios(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = _now()
    prices = fetch_prices(cfg.esios_token, now.date())
    if not prices:
        await update.message.reply_text("Aún no hay precios.")
        return
    lines = []
    for day in sorted({h.date() for h in prices}):
        day_p = {h: p for h, p in prices.items() if h.date() == day}
        cheap = sorted(day_p.items(), key=lambda x: x[1])[:3]
        avg = sum(day_p.values()) / len(day_p)
        lines.append(f"📅 {day:%d/%m}: media {avg:.3f} €/kWh\n   más baratas: " +
                     ", ".join(f"{h:%H}h ({p:.3f})" for h, p in sorted(cheap)))
    await update.message.reply_text("\n".join(lines))


async def cargar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        cur, tgt, hhmm = int(ctx.args[0]), int(ctx.args[1]), ctx.args[2]
        t = time.fromisoformat(hhmm)
        assert 0 <= cur <= 100 and 0 <= tgt <= 100
    except Exception:
        await update.message.reply_text("Uso: /cargar 30 80 07:30")
        return
    now = _now()
    deadline = datetime.combine(now.date(), t, ZoneInfo(TZ))
    if deadline <= now:
        deadline += timedelta(days=1)
    prices = fetch_prices(cfg.esios_token, now.date())
    plan = plan_charge(prices, now, deadline, cur, tgt, cfg.battery_kwh, cfg.charger_kw, cfg.efficiency)
    if not plan.hours:
        await update.message.reply_text("Ya tienes batería suficiente 👍" if plan.feasible else "Sin precios disponibles.")
        return
    msg = (f"🔌 {cur}% → {tgt}% para las {deadline:%a %H:%M}\n"
           f"Energía: {plan.kwh_needed:.1f} kWh · Coste ≈ {plan.cost:.2f} €\n"
           f"Carga en: {_fmt_hours(plan.hours)}")
    if not plan.feasible:
        msg += "\n⚠️ No llegas al objetivo con los precios/horas disponibles (el precio de mañana sale ~20:30)."
    await update.message.reply_text(msg)


def main():
    global cfg
    logging.basicConfig(level=logging.INFO)
    cfg = cfg_mod.load()
    app = Application.builder().token(cfg.telegram_token).build()
    only_me = filters.Chat(cfg.chat_id)
    app.add_handler(CommandHandler(["start", "help"], start, only_me))
    app.add_handler(CommandHandler("precios", precios, only_me))
    app.add_handler(CommandHandler("cargar", cargar, only_me))
    url = os.getenv("RENDER_EXTERNAL_URL")
    if url:  # Render gratis: webhook, el servicio se duerme y Telegram lo despierta
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "10000")),
                        url_path=cfg.webhook_secret, secret_token=cfg.webhook_secret,
                        webhook_url=f"{url}/{cfg.webhook_secret}")
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
