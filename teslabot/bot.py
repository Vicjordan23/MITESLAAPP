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
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _now() -> datetime:
    return datetime.now(ZoneInfo(TZ))


def _dia(d: datetime, now: datetime) -> str:
    delta = (d.date() - now.date()).days
    return {0: "hoy", 1: "mañana"}.get(delta, DIAS[d.weekday()])


def _fmt_hours(hours: list[datetime], now: datetime | None = None) -> str:
    """Agrupa horas consecutivas: 'hoy 22:00 → 02:00', 'mañana 14:00 → 15:00'."""
    if not hours:
        return "—"
    now = now or _now()
    runs, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h - prev != timedelta(hours=1):
            runs.append((start, prev)); start = h
        prev = h
    runs.append((start, prev))
    return "\n".join(f"   • {_dia(a, now)} {a:%H:%M} → {b + timedelta(hours=1):%H:%M}" for a, b in runs)


AYUDA = (
    "👋 ¡Hola! Te ayudo a cargar el Tesla cuando la luz está más barata.\n\n"
    "🔌 /cargar — dime cuánta batería tienes, cuánta quieres y a qué hora vas a coger el coche.\n"
    "   Ejemplo: /cargar 30 80 07:30\n"
    "   (tengo el 30%, quiero el 80% y salgo a las 7:30)\n\n"
    "💶 /precios — el precio de la luz de hoy y mañana y las horas más baratas."
)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(AYUDA)


async def precios(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = _now()
    prices = fetch_prices(cfg.esios_token, now.date())
    if not prices:
        await update.message.reply_text("Todavía no hay precios publicados.")
        return
    lines = ["💶 Precio de la luz (€ por kWh, ya con peajes y cargos)\n"]
    for day in sorted({h.date() for h in prices}):
        day_p = {h: p for h, p in prices.items() if h.date() == day}
        cheap = sorted(day_p.items(), key=lambda x: x[1])[:3]
        dear = max(day_p.items(), key=lambda x: x[1])
        avg = sum(day_p.values()) / len(day_p)
        name = _dia(datetime.combine(day, time.min, ZoneInfo(TZ)), now)
        lines.append(f"📅 {name.capitalize()} ({day:%d/%m}) — media {avg:.3f} €\n"
                     f"   ✅ Más baratas: " + ", ".join(f"{h:%H}h ({p:.3f})" for h, p in sorted(cheap)) +
                     f"\n   ❌ Más cara: {dear[0]:%H}h ({dear[1]:.3f})")
    if now.date() + timedelta(days=1) not in {h.date() for h in prices}:
        lines.append("\nℹ️ Los precios de mañana se publican sobre las 20:30.")
    await update.message.reply_text("\n".join(lines))


async def cargar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        cur, tgt, hhmm = int(ctx.args[0]), int(ctx.args[1]), ctx.args[2]
        t = time.fromisoformat(hhmm)
        assert 0 <= cur <= 100 and 0 <= tgt <= 100
    except Exception:
        await update.message.reply_text(
            "Necesito tres datos separados por espacios:\n"
            "1️⃣ batería que tienes ahora (%)\n2️⃣ batería que quieres (%)\n3️⃣ hora a la que lo cogerás\n\n"
            "Ejemplo: /cargar 30 80 07:30")
        return
    now = _now()
    deadline = datetime.combine(now.date(), t, ZoneInfo(TZ))
    if deadline <= now:
        deadline += timedelta(days=1)
    prices = fetch_prices(cfg.esios_token, now.date())
    plan = plan_charge(prices, now, deadline, cur, tgt, cfg.battery_kwh, cfg.car_kw, cfg.efficiency)
    if tgt <= cur:
        await update.message.reply_text(f"Ya tienes {cur}%, no hace falta cargar nada 👍")
        return
    if not prices:
        await update.message.reply_text("Todavía no hay precios publicados.")
        return
    hours = len(plan.hours)
    msg = [f"🚗 Quieres pasar del {cur}% al {tgt}% para el {_dia(deadline, now)} a las {deadline:%H:%M}.\n",
           f"⚡ Necesitas {plan.kwh_needed:.1f} kWh. Con {cfg.car_kw:g} kW de carga son ≈ {plan.kwh_needed / cfg.car_kw:.1f} h.\n",
           "🕒 Te conviene cargar en estas horas:", _fmt_hours(plan.hours, now),
           f"\n💶 Coste estimado: {plan.cost:.2f} € (sin IVA ni impuestos)"]
    saving = plan.cost_asap - plan.cost
    if plan.covered and saving > 0.05:
        msg.append(f"✨ Ahorras {saving:.2f} € frente a cargar ya mismo.")
    if not plan.covered:
        msg.append("\n⚠️ Aún no sé el precio de las horas hasta esa hora (los de mañana salen sobre las 20:30). "
                   "Esto es provisional: vuelve a preguntarme después de las 20:30.")
    elif not plan.feasible:
        msg.append("\n⚠️ No da tiempo a llegar a ese porcentaje antes de la hora indicada. "
                   "Te muestro lo máximo que puedes cargar.")
    await update.message.reply_text("\n".join(msg))


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
