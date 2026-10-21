import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters

from . import config as cfg_mod
from .config import TZ
from .planner import best_window, plan_charge
from .prices import fetch_real_prices

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
    "Usa /menu para ver todas las opciones con botones."
)

DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
BTN = InlineKeyboardButton


def _kb(rows):
    return InlineKeyboardMarkup(rows)


def _grid(buttons, per_row):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


MENU_TEXT = "🚗 ¿Qué quieres hacer?"
MENU_KB = _kb([
    [BTN("🔌 Cargar el coche", callback_data="c")],
    [BTN("💶 Precios de la luz", callback_data="p")],
    [BTN("⏱ ¿Cuándo es más barato?", callback_data="n")],
    [BTN("🧺 Mejor hora para electrodomésticos", callback_data="w")],
    [BTN("⚙️ Mis ajustes", callback_data="s")],
])
BACK = [BTN("⬅️ Menú", callback_data="m")]


def _prices():
    return fetch_real_prices(cfg.esios_token, _now().date())


def _allowed(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.id == cfg.chat_id


def prices_text(now: datetime) -> str:
    prices = _prices()
    if not prices:
        return "Todavía no hay precios publicados."
    lines = ["💶 Precio de la luz (€ por kWh, con peajes, cargos e impuestos: lo que pagas de verdad)\n"]
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
    return "\n".join(lines)


def plan_text(cur: int, tgt: int, deadline: datetime, now: datetime) -> str:
    if tgt <= cur:
        return f"Ya tienes {cur}%, no hace falta cargar nada 👍"
    prices = _prices()
    if not prices:
        return "Todavía no hay precios publicados."
    plan = plan_charge(prices, now, deadline, cur, tgt, cfg.battery_kwh, cfg.car_kw, cfg.efficiency)
    msg = [f"🚗 Quieres pasar del {cur}% al {tgt}% para {_dia(deadline, now)} a las {deadline:%H:%M}.\n",
           f"⚡ Necesitas {plan.kwh_needed:.1f} kWh. Con {cfg.car_kw:g} kW de carga son ≈ {plan.kwh_needed / cfg.car_kw:.1f} h.\n",
           f"🛣 Añades ≈ {(tgt - cur) / 100 * cfg.battery_kwh / cfg.kwh_per_100km * 100:.0f} km de autonomía.\n",
           "🕒 Te conviene cargar en estas horas:", _fmt_hours(plan.hours, now),
           f"\n💶 Coste estimado: {plan.cost:.2f} € (con IVA e impuesto eléctrico, solo energía)"]
    saving = plan.cost_asap - plan.cost
    if plan.covered and saving > 0.05:
        msg.append(f"✨ Ahorras {saving:.2f} € frente a cargar ya mismo.")
    if not plan.covered:
        msg.append("\n⚠️ Aún no sé el precio de las horas hasta esa hora (los de mañana salen sobre las 20:30). "
                   "Esto es provisional: vuelve a preguntarme después de las 20:30.")
    elif not plan.feasible:
        msg.append("\n⚠️ No da tiempo a llegar a ese porcentaje antes de la hora indicada. "
                   "Te muestro lo máximo que puedes cargar.")
    return "\n".join(msg)


async def _show(update: Update, text: str, kb):
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _show(update, MENU_TEXT, MENU_KB)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(AYUDA, reply_markup=MENU_KB)


async def precios(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _show(update, prices_text(_now()), _kb([BACK]))


async def cargar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/cargar sin datos abre el asistente; /cargar 30 80 07:30 va directo."""
    if ctx.args and len(ctx.args) >= 3:
        try:
            cur, tgt, t = int(ctx.args[0]), int(ctx.args[1]), time.fromisoformat(ctx.args[2])
            now = _now()
            deadline = datetime.combine(now.date(), t, ZoneInfo(TZ))
            if deadline <= now:
                deadline += timedelta(days=1)
            await update.message.reply_text(plan_text(cur, tgt, deadline, now), reply_markup=_kb([BACK]))
            return
        except ValueError:
            pass
    await ask_battery(update)


async def ask_battery(update: Update):
    btns = [BTN(f"{n}%", callback_data=f"a|{n}") for n in range(5, 100, 5)]
    await _show(update, "🔋 ¿Cuánta batería tiene el coche ahora?", _kb(_grid(btns, 5) + [BACK]))


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    parts = update.callback_query.data.split("|")
    k, a = parts[0], parts[1:]
    now = _now()
    try:
        if k == "m":
            await _show(update, MENU_TEXT, MENU_KB)
        elif k == "p":
            await _show(update, prices_text(now), _kb([BACK]))
        elif k == "s":
            await _show(update,
                        f"⚙️ Ajustes\n\n🔋 Batería: {cfg.battery_kwh:g} kWh\n"
                        f"🔌 Cargador: hasta {cfg.charger_kw:g} kW\n"
                        f"🏠 Potencia contratada: {cfg.contracted_kw:g} kW (reservo {cfg.house_kw:g} kW para la casa)\n"
                        f"➡️ Potencia usada para el coche: {cfg.car_kw:g} kW\n\n"
                        "Para cambiarlos hay que editarlos en Render (variables BATTERY_KWH, CHARGER_KW, CONTRACTED_KW).",
                        _kb([BACK]))
        elif k == "n":
            prices = _prices()
            cheap = sorted(h for h, _ in sorted(((h, p) for h, p in prices.items() if h + timedelta(hours=1) > now),
                                              key=lambda x: x[1])[:5])
            text = ("⏱ Las 5 horas más baratas desde ahora:\n" + _fmt_hours(cheap, now)) if cheap else "Sin precios."
            await _show(update, text, _kb([BACK]))
        elif k == "w":
            if not a:
                await _show(update, "🧺 ¿Cuántas horas dura el aparato (lavadora, lavavajillas...)?",
                            _kb([[BTN(f"{n} h", callback_data=f"w|{n}") for n in (1, 2, 3, 4)], BACK]))
            else:
                best = best_window(_prices(), now, int(a[0]))
                text = (f"🧺 Lo más barato en las próximas 24 h: empezar {_dia(best[0], now)} a las {best[0]:%H:%M} "
                        f"(media {best[1]:.3f} €/kWh)") if best else "Aún no hay precios suficientes."
                await _show(update, text, _kb([BACK]))
        elif k == "c":
            await ask_battery(update)
        elif k == "a":  # batería actual elegida
            cur = int(a[0])
            btns = [BTN(f"{n}%", callback_data=f"b|{cur}|{n}") for n in range(max(cur + 5, 50), 101, 5)]
            await _show(update, f"🔋 Tienes {cur}%.\n🎯 ¿Cuánta batería quieres tener al salir?",
                        _kb(_grid(btns, 4) + [BACK]))
        elif k == "b":  # objetivo elegido → día
            cur, tgt = a
            btns = []
            for off in range(7):
                d = now + timedelta(days=off)
                label = "Hoy" if off == 0 else "Mañana" if off == 1 else f"{DIAS_CORTO[d.weekday()]} {d:%d/%m}"
                btns.append(BTN(label, callback_data=f"d|{cur}|{tgt}|{off}"))
            await _show(update, f"🔋 {cur}% → {tgt}%\n📅 ¿Qué día vas a coger el coche?", _kb(_grid(btns, 3) + [BACK]))
        elif k in ("d", "H"):  # día elegido (o más horas) → hora
            cur, tgt, off = a
            hours = list(range(5, 13)) if k == "d" else list(range(13, 24)) + list(range(0, 5))
            btns = [BTN(f"{h:02d}h", callback_data=f"h|{cur}|{tgt}|{off}|{h}") for h in hours]
            more = [] if k == "H" else [BTN("🕒 Más horas", callback_data=f"H|{cur}|{tgt}|{off}")]
            await _show(update, "⏰ ¿A qué hora vas a salir?", _kb(_grid(btns, 4) + [more or [BTN("⬅️ Horas de la mañana", callback_data=f"d|{cur}|{tgt}|{off}")], BACK]))
        elif k == "h":  # hora elegida → minutos
            cur, tgt, off, h = a
            btns = [BTN(f":{m:02d}", callback_data=f"r|{cur}|{tgt}|{off}|{h}|{m}") for m in (0, 15, 30, 45)]
            await _show(update, f"⏰ A las {int(h):02d}:__ ¿y los minutos?", _kb([btns, BACK]))
        elif k == "r":  # todo elegido → resultado
            cur, tgt, off, h, m = map(int, a)
            deadline = datetime.combine(now.date() + timedelta(days=off), time(h, m), ZoneInfo(TZ))
            if deadline <= now:
                await _show(update, "Esa hora ya ha pasado 🙈 Elige otra.", _kb([[BTN("🔌 Empezar de nuevo", callback_data="c")], BACK]))
            else:
                await _show(update, plan_text(cur, tgt, deadline, now),
                            _kb([[BTN("🔄 Recalcular", callback_data=update.callback_query.data)],
                                 [BTN("🔌 Otra carga", callback_data="c")], BACK]))
    except Exception:
        log.exception("error en botón %s", update.callback_query.data)
        await _show(update, "😕 Algo ha fallado al consultar los precios. Inténtalo de nuevo en un momento.", _kb([BACK]))


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("menu", "Abrir el menú"),
        BotCommand("cargar", "Planificar la carga del coche"),
        BotCommand("precios", "Precios de la luz hoy y mañana"),
    ])


def main():
    global cfg
    logging.basicConfig(level=logging.INFO)
    cfg = cfg_mod.load()
    app = Application.builder().token(cfg.telegram_token).post_init(post_init).build()
    only_me = filters.Chat(cfg.chat_id)
    app.add_handler(CommandHandler(["start", "help"], start, only_me))
    app.add_handler(CommandHandler("menu", menu, only_me))
    app.add_handler(CommandHandler("precios", precios, only_me))
    app.add_handler(CommandHandler("cargar", cargar, only_me))
    app.add_handler(CallbackQueryHandler(on_button))
    url = os.getenv("RENDER_EXTERNAL_URL")
    if url:  # Render gratis: webhook, el servicio se duerme y Telegram lo despierta
        app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", "10000")),
                        url_path=cfg.webhook_secret, secret_token=cfg.webhook_secret,
                        webhook_url=f"{url}/{cfg.webhook_secret}")
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
