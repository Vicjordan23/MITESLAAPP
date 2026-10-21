import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters

from . import car, charger, core, store
from . import config as cfg_mod
from .config import TZ
from .core import dia as _dia
from .core import fmt_hours as _fmt_hours
from .core import now as _now
from .planner import best_window, plan_charge
from .prices import fetch_prices

log = logging.getLogger("teslabot")
base_cfg = None
cfg = None  # configuración efectiva (variables de entorno + ajustes guardados en Telegram)
BTN = InlineKeyboardButton
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

AYUDA = ("👋 ¡Hola! Te ayudo a cargar el Tesla cuando la luz está más barata.\n\n"
         "Usa /menu para ver todas las opciones con botones.")
MENU_TEXT = "🚗 ¿Qué quieres hacer?"


def _kb(rows):
    return InlineKeyboardMarkup(rows)


def _grid(buttons, per_row):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


MENU_KB = _kb([
    [BTN("🔌 Cargar el coche", callback_data="c")],
    [BTN("💶 Precios de la luz", callback_data="p"), BTN("⏱ ¿Cuándo es barato?", callback_data="n")],
    [BTN("🚗 Estado del coche", callback_data="v"), BTN("🔌 Cargador", callback_data="k")],
    [BTN("🧺 Electrodomésticos", callback_data="w"), BTN("📊 Resumen del mes", callback_data="r")],
    [BTN("⚙️ Ajustes", callback_data="s")],
])
BACK = [BTN("⬅️ Menú", callback_data="m")]


def _refresh() -> dict:
    """Recarga los ajustes guardados en Telegram (por si cambiaron desde otro sitio) y devuelve todos los datos."""
    global cfg
    cfg, data = core.load_all(base_cfg)
    return data


def _prices(days: int = 2):
    return fetch_prices(cfg.esios_token, _now().date(), days)


def _allowed(update: Update) -> bool:
    return update.effective_chat is not None and update.effective_chat.id == cfg.chat_id


# ---------- textos ----------

def prices_text(now: datetime) -> str:
    prices = _prices()
    if not prices:
        return "Todavía no hay precios publicados."
    lines = ["💶 Precio de la luz (€ por kWh, precio base sin impuestos)\n"]
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


def plan_text(cur: int, tgt: int, deadline: datetime, now: datetime):
    """Devuelve (texto, Plan|None)."""
    if tgt <= cur:
        return f"Ya tienes {cur}%, no hace falta cargar nada 👍", None
    prices = _prices()
    if not prices:
        return "Todavía no hay precios publicados.", None
    plan = plan_charge(prices, now, deadline, cur, tgt, cfg.battery_kwh, cfg.car_kw, cfg.efficiency)
    km = (tgt - cur) / 100 * cfg.battery_kwh / cfg.kwh_per_100km * 100
    msg = [f"🚗 Quieres pasar del {cur}% al {tgt}% para {_dia(deadline, now)} a las {deadline:%H:%M}.\n",
           f"⚡ Necesitas {plan.kwh_needed:.1f} kWh. Con {cfg.car_kw:g} kW de carga son ≈ {plan.kwh_needed / cfg.car_kw:.1f} h.",
           f"🛣 Añades ≈ {km:.0f} km de autonomía.\n",
           "🕒 Te conviene cargar en estas horas:", _fmt_hours(plan.hours, now),
           f"\n💶 Coste estimado: {plan.cost:.2f} € (precio base, sin impuestos)"]
    saving = plan.cost_asap - plan.cost
    if plan.covered and saving > 0.05:
        msg.append(f"✨ Ahorras {saving:.2f} € frente a cargar ya mismo.")
    if not plan.covered:
        msg.append("\n⚠️ Aún no sé el precio de las horas hasta esa hora (los de mañana salen sobre las 20:30). "
                   "Es provisional: si lo programas, lo actualizo yo solo a las 20:35.")
    elif not plan.feasible:
        msg.append("\n⚠️ No da tiempo a llegar a ese porcentaje antes de la hora indicada. "
                   "Te muestro lo máximo que puedes cargar.")
    return "\n".join(msg), plan


def settings_text() -> str:
    return (f"⚙️ Ajustes (toca uno para cambiarlo)\n\n"
            f"🔋 Batería: {cfg.battery_kwh:g} kWh\n"
            f"🔌 Cargador: hasta {cfg.charger_kw:g} kW\n"
            f"🏠 Potencia contratada: {cfg.contracted_kw:g} kW\n"
            f"🏠 Reserva para la casa: {cfg.house_kw:g} kW\n"
            f"➡️ Potencia usada para el coche: {cfg.car_kw:g} kW\n"
            f"🛣 Consumo: {cfg.kwh_per_100km:g} kWh/100 km\n"
            f"🔔 Avisos de día barato/caro: {'sí' if cfg.alerts else 'no'} "
            f"(barato ≤ {cfg.alert_low:g} €, caro ≥ {cfg.alert_high:g} €)")


SETTING_LABELS = {
    "battery_kwh": ("🔋 Batería (kWh)", [55, 60, 75, 78]),
    "charger_kw": ("🔌 Cargador (kW)", [2.3, 3.7, 7.4, 11]),
    "contracted_kw": ("🏠 Potencia contratada (kW)", [3.3, 4.4, 5.5, 6.9, 9.2]),
    "house_kw": ("🏠 Reserva casa (kW)", [0.5, 1, 1.5, 2]),
    "kwh_per_100km": ("🛣 Consumo (kWh/100 km)", [13, 14, 15, 16, 17, 18]),
    "alert_low": ("🟢 Umbral día barato (€/kWh)", [0.03, 0.05, 0.08, 0.10, 0.12]),
    "alert_high": ("🔴 Umbral día caro (€/kWh)", [0.15, 0.18, 0.20, 0.25]),
}


def settings_kb():
    rows = [[BTN(label, callback_data=f"s|{k}")] for k, (label, _) in SETTING_LABELS.items()]
    rows.append([BTN("🔔 Avisos: " + ("activados ✅" if cfg.alerts else "desactivados ❌") + " (tocar para cambiar)",
                     callback_data=f"s|alerts|{0 if cfg.alerts else 1}")])
    return _kb(rows + [BACK])


def month_summary(data: dict, now: datetime) -> str:
    rows = [h for h in data.get("hist", []) if h[0][:7] == f"{now:%Y-%m}"]
    if not rows:
        return ("📊 Todavía no hay cargas este mes.\n\nCuando programes una carga (botón 📌 al calcularla) "
                "se apunta aquí.")
    kwh, cost, asap = sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows)
    return (f"📊 Resumen de {DIAS_MES[now.month - 1]}\n\n"
            f"🔌 Cargas programadas: {len(rows)}\n⚡ Energía: {kwh:.0f} kWh\n"
            f"💶 Coste: {cost:.2f} € (media {cost / kwh:.3f} €/kWh, precio base sin impuestos)\n"
            f"✨ Ahorro vs. cargar ya mismo: {asap - cost:.2f} €\n"
            f"🛣 ≈ {kwh * cfg.efficiency / cfg.kwh_per_100km * 100:.0f} km\n\n"
            "ℹ️ Es una estimación a partir de las cargas que programas, no una medición real del cargador.")


DIAS_MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
            "noviembre", "diciembre"]


# ---------- envío ----------

async def _show(update: Update, text: str, kb):
    q = update.callback_query
    if q:
        await q.answer()
        await q.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _refresh()
    await _show(update, MENU_TEXT, MENU_KB)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _refresh()
    await update.message.reply_text(AYUDA, reply_markup=MENU_KB)


async def precios(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _refresh()
    await _show(update, prices_text(_now()), _kb([BACK]))


async def cargar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/cargar sin datos abre el asistente; /cargar 30 80 07:30 va directo."""
    _refresh()
    if ctx.args and len(ctx.args) >= 3:
        try:
            cur, tgt, t = int(ctx.args[0]), int(ctx.args[1]), time.fromisoformat(ctx.args[2])
            now = _now()
            deadline = datetime.combine(now.date(), t, ZoneInfo(TZ))
            if deadline <= now:
                deadline += timedelta(days=1)
            await update.message.reply_text(plan_text(cur, tgt, deadline, now)[0], reply_markup=_kb([BACK]))
            return
        except ValueError:
            pass
    await ask_battery(update)


async def ask_battery(update: Update):
    try:  # si el coche está enlazado, uso su batería real y me salto la pregunta
        st = car.status()
        if st and st.get("soc") is not None:
            await _ask_target(update, int(st["soc"]), f"🔋 Tu Tesla tiene {st['soc']}% (dato real).")
            return
    except Exception:
        log.exception("no pude leer el coche")
    btns = [BTN(f"{n}%", callback_data=f"a|{n}") for n in range(5, 100, 5)]
    await _show(update, "🔋 ¿Cuánta batería tiene el coche ahora?", _kb(_grid(btns, 5) + [BACK]))


async def _ask_target(update: Update, cur: int, intro: str):
    btns = [BTN(f"{n}%", callback_data=f"b|{cur}|{n}") for n in range(max(cur + 5, 50), 101, 5)]
    await _show(update, f"{intro}\n🎯 ¿Cuánta batería quieres tener al salir?", _kb(_grid(btns, 4) + [BACK]))


def _save(fn):
    return store.update(base_cfg.telegram_token, base_cfg.chat_id, fn)


# ---------- botones ----------

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return
    data_cb = update.callback_query.data
    parts = data_cb.split("|")
    k, a = parts[0], parts[1:]
    now = _now()
    stored = _refresh()
    try:
        if k == "m":
            await _show(update, MENU_TEXT, MENU_KB)
        elif k == "p":
            await _show(update, prices_text(now), _kb([BACK]))
        elif k == "n":
            prices = _prices()
            cheap = sorted(h for h, _ in sorted(((h, p) for h, p in prices.items() if h + timedelta(hours=1) > now),
                                              key=lambda x: x[1])[:5])
            await _show(update, ("⏱ Las 5 horas más baratas desde ahora:\n" + _fmt_hours(cheap, now)) if cheap
                        else "Sin precios.", _kb([BACK]))
        elif k == "w":
            if not a:
                await _show(update, "🧺 ¿Cuántas horas dura el aparato (lavadora, lavavajillas...)?",
                            _kb([[BTN(f"{n} h", callback_data=f"w|{n}") for n in (1, 2, 3, 4)], BACK]))
            else:
                best = best_window(_prices(), now, int(a[0]))
                text = (f"🧺 Lo más barato en las próximas 24 h: empezar {_dia(best[0], now)} a las {best[0]:%H:%M} "
                        f"(media {best[1]:.3f} €/kWh)") if best else "Aún no hay precios suficientes."
                await _show(update, text, _kb([BACK]))
        elif k == "s":
            if not a:
                await _show(update, settings_text(), settings_kb())
            elif len(a) == 1:  # elegir valor de un ajuste
                label, opts = SETTING_LABELS[a[0]]
                cur_v = getattr(cfg, a[0])
                btns = [BTN(("✅ " if float(o) == cur_v else "") + f"{o:g}", callback_data=f"s|{a[0]}|{o:g}") for o in opts]
                await _show(update, f"{label}\nValor actual: {cur_v:g}", _kb(_grid(btns, 3) + [[BTN("⬅️ Ajustes", callback_data="s")]]))
            else:  # guardar
                key, val = a
                v = int(float(val)) if key == "alerts" else float(val)
                _save(lambda d: d.setdefault("settings", {}).__setitem__(key, v))
                _refresh()
                await _show(update, "✅ Guardado.\n\n" + settings_text(), settings_kb())
        elif k == "c":
            await ask_battery(update)
        elif k == "a":
            await _ask_target(update, int(a[0]), f"🔋 Tienes {a[0]}%.")
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
            other = ([BTN("🕒 Más horas", callback_data=f"H|{cur}|{tgt}|{off}")] if k == "d"
                     else [BTN("⬅️ Horas de la mañana", callback_data=f"d|{cur}|{tgt}|{off}")])
            await _show(update, "⏰ ¿A qué hora vas a salir?", _kb(_grid(btns, 4) + [other, BACK]))
        elif k == "h":  # hora elegida → minutos
            cur, tgt, off, h = a
            btns = [BTN(f":{m:02d}", callback_data=f"r|{cur}|{tgt}|{off}|{h}|{m}") for m in (0, 15, 30, 45)]
            await _show(update, f"⏰ A las {int(h):02d}:__ ¿y los minutos?", _kb([btns, BACK]))
        elif k in ("r", "g") and len(a) == 5:  # resultado (r) o programar (g)
            cur, tgt, off, h, m = map(int, a)
            deadline = datetime.combine(now.date() + timedelta(days=off), time(h, m), ZoneInfo(TZ))
            if deadline <= now:
                await _show(update, "Esa hora ya ha pasado 🙈 Elige otra.",
                            _kb([[BTN("🔌 Empezar de nuevo", callback_data="c")], BACK]))
                return
            text, plan = plan_text(cur, tgt, deadline, now)
            if k == "r":
                rows = [[BTN("🔄 Recalcular", callback_data=data_cb)]]
                if plan and plan.hours:
                    rows.insert(0, [BTN("📌 Programar esta carga", callback_data="g" + data_cb[1:])])
                await _show(update, text, _kb(rows + [[BTN("🔌 Otra carga", callback_data="c")], BACK]))
            else:
                rec = core.plan_record(plan, cur, tgt, deadline)
                _save(lambda d: (d.__setitem__("plan", rec), core.add_history(d, rec)))
                how = ("encenderé y pausaré el Wallbox solo" if charger.configured()
                       else "te avisaré por aquí de cuándo conectar y desconectar el coche")
                await _show(update, f"📌 Carga programada.\n\n{text}\n\n✅ {how}.",
                            _kb([[BTN("🚗 Ver estado", callback_data="v")], BACK]))
        elif k == "v":
            lines = ["🚗 Estado"]
            try:
                st = car.status() if car.configured() else None
            except Exception:
                st = None
                lines.append("⚠️ No pude leer el coche ahora mismo.")
            if st:
                lines.append(f"🔋 Batería: {st['soc']}% · {'enchufado' if st['plugged'] else 'sin enchufar'}"
                             f" · límite {st['limit']}%")
            else:
                lines.append("🔋 Coche no enlazado: cuando lo tengas, añade TESSIE_TOKEN y TESSIE_VIN y leeré la batería sola.")
            plan = stored.get("plan")
            rows = []
            if plan:
                lines.append(f"\n📌 Carga programada: {plan['cur']}% → {plan['tgt']}% para "
                             f"{_dia(datetime.fromisoformat(plan['dl']), now)} {datetime.fromisoformat(plan['dl']):%H:%M}"
                             f"{' (provisional)' if plan.get('prov') else ''}\n"
                             f"{_fmt_hours(sorted(core.plan_hours(plan)), now)}\n💶 ≈ {plan['cost']:.2f} €")
                rows.append([BTN("🗑 Cancelar carga programada", callback_data="x")])
            else:
                lines.append("\n📌 No hay ninguna carga programada.")
            await _show(update, "\n".join(lines), _kb(rows + [BACK]))
        elif k == "x":
            _save(lambda d: d.pop("plan", None))
            await _show(update, "🗑 Carga programada cancelada.", _kb([BACK]))
        elif k == "k":
            if not charger.configured():
                await _show(update,
                            "🔌 Cargador no enlazado todavía.\n\nCuando lo instalen, añade en Render y en los secrets de "
                            "GitHub WALLBOX_USER y WALLBOX_PASSWORD (tu cuenta de myWallbox). Entonces encenderé y pausaré "
                            "la carga solo en las horas baratas.\n\nMientras tanto, si programas una carga, te aviso para "
                            "que conectes y desconectes a mano.", _kb([BACK]))
            else:
                try:
                    if a:
                        charger.set_charging(a[0] == "1")
                    s = charger.status()
                    txt = ("🔌 Wallbox\n" + "\n".join(f"• {k2}: {v}" for k2, v in s.items()))
                except Exception as e:
                    txt = f"⚠️ No pude hablar con el Wallbox: {e}"
                await _show(update, txt, _kb([[BTN("▶️ Reanudar", callback_data="k|1"), BTN("⏸ Pausar", callback_data="k|0")],
                                              [BTN("🔄 Actualizar", callback_data="k")], BACK]))
        elif k == "r":
            await _show(update, month_summary(stored, now), _kb([BACK]))
    except Exception:
        log.exception("error en botón %s", data_cb)
        await _show(update, "😕 Algo ha fallado. Inténtalo de nuevo en un momento.", _kb([BACK]))


async def post_init(app: Application):
    await app.bot.set_my_commands([
        BotCommand("menu", "Abrir el menú"),
        BotCommand("cargar", "Planificar la carga del coche"),
        BotCommand("precios", "Precios de la luz hoy y mañana"),
    ])


def main():
    global base_cfg, cfg
    logging.basicConfig(level=logging.INFO)
    base_cfg = cfg = cfg_mod.load()
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
