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


def fmt_hours(hours: list[datetime], ref: datetime | None = None) -> str:
    """Agrupa horas consecutivas: '• hoy 22:00 → 02:00'."""
    if not hours:
        return "—"
    ref = ref or now()
    hours = sorted(hours)
    runs, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h - prev != timedelta(hours=1):
            runs.append((start, prev)); start = h
        prev = h
    runs.append((start, prev))
    return "\n".join(f"   • {dia(a, ref)} {a:%H:%M} → {b + timedelta(hours=1):%H:%M}" for a, b in runs)


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
