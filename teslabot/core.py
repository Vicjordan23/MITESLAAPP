"""Piezas compartidas por el bot (Render), el aviso diario y el control horario (GitHub Actions)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import store
from .config import Config, TZ
from .planner import Plan

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
HIST_MAX = 40


def now() -> datetime:
    return datetime.now(ZoneInfo(TZ))


def dia(d: datetime, ref: datetime) -> str:
    delta = (d.date() - ref.date()).days
    return {0: "hoy", 1: "mañana"}.get(delta, DIAS[d.weekday()])


def fmt_hours(hours: list[datetime], ref: datetime | None = None, prices: dict | None = None) -> str:
    """Sin precios agrupa horas seguidas ('• hoy 22:00 → 02:00'); con precios lista cada hora con su precio."""
    if not hours:
        return "—"
    ref = ref or now()
    hours = sorted(hours)
    if prices:
        return "\n".join(
            f"   • {dia(h, ref)} {h:%H:%M}-{(h + timedelta(hours=1)):%H:%M} → "
            + (f"{prices[h]:.3f} €/kWh" if h in prices else "—") for h in hours)
    runs, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h - prev != timedelta(hours=1):
            runs.append((start, prev)); start = h
        prev = h
    runs.append((start, prev))
    return "\n".join(f"   • {dia(a, ref)} {a:%H:%M} → {b + timedelta(hours=1):%H:%M}" for a, b in runs)


def day_table(prices: dict, day, ref: datetime) -> str:
    """Los 24 precios de un día, con semáforo (tercio más barato 🟢, más caro 🔴)."""
    day_p = sorted((h, p) for h, p in prices.items() if h.date() == day)
    if not day_p:
        return "Aún no hay precios de ese día."
    vals = sorted(p for _, p in day_p)
    lo, hi = vals[len(vals) // 3], vals[(2 * len(vals)) // 3]
    lines = [f"📋 {dia(day_p[0][0], ref).capitalize()} ({day:%d/%m}) — € por kWh, precio base\n"]
    for h, p in day_p:
        dot = "🟢" if p <= lo else "🔴" if p >= hi else "🟡"
        lines.append(f"{dot} {h:%H}-{(h + timedelta(hours=1)):%H}h  {p:.3f}")
    return "\n".join(lines)


def load_all(base: Config) -> tuple[Config, dict]:
    data = store.load(base.telegram_token, base.chat_id)
    return base.with_overrides(data.get("settings", {})), data


def plan_record(plan: Plan, cur: int, tgt: int, deadline: datetime) -> dict:
    return {"cur": cur, "tgt": tgt, "dl": deadline.isoformat(timespec="minutes"),
            "hours": [h.isoformat(timespec="minutes") for h in plan.hours],
            "kwh": round(plan.kwh_needed, 1), "cost": round(plan.cost, 2), "asap": round(plan.cost_asap, 2),
            "prov": not plan.covered, "sent": []}


def plan_hours(record: dict) -> set[datetime]:
    return {datetime.fromisoformat(h) for h in record.get("hours", [])}


def add_history(data: dict, record: dict) -> None:
    hist = [h for h in data.get("hist", []) if h[0] != record["dl"]]  # misma salida → se reemplaza
    hist.append([record["dl"], record["kwh"], record["cost"], record["asap"]])
    data["hist"] = hist[-HIST_MAX:]
