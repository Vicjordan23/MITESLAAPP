"""Elige las horas más baratas para cargar antes de una hora límite."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import math


@dataclass
class Plan:
    hours: list[datetime]   # inicios de hora elegidos, ordenados
    kwh_needed: float       # energía a tomar de la red
    cost: float             # € estimados
    feasible: bool          # False si no caben las horas necesarias antes del límite
    cost_asap: float = 0.0  # € si empezaras a cargar ya, sin esperar a las horas baratas
    covered: bool = True    # False si aún no hay precios hasta la hora límite


def energy_needed(current: int, target: int, battery_kwh: float, efficiency: float) -> float:
    return max(target - current, 0) / 100 * battery_kwh / efficiency


def plan_charge(prices: dict[datetime, float], now: datetime, deadline: datetime,
                current: int, target: int, battery_kwh: float,
                charger_kw: float, efficiency: float) -> Plan:
    kwh = energy_needed(current, target, battery_kwh, efficiency)
    n_hours = math.ceil(kwh / charger_kw) if kwh > 0 else 0
    slot_end = lambda h: h + timedelta(hours=1)
    candidates = [(p, h) for h, p in prices.items() if slot_end(h) > now and h < deadline]
    chosen = sorted(candidates)[:n_hours]
    chosen.sort(key=lambda x: x[1])
    covered = bool(prices) and max(prices) + timedelta(hours=1) >= deadline
    asap = [p for _, p in sorted((h, p) for p, h in candidates)[:n_hours]]
    return Plan([h for _, h in chosen], kwh, _cost([p for p, _ in sorted(chosen)], kwh, charger_kw),
                len(chosen) == n_hours, _cost(asap, kwh, charger_kw), covered)


def _cost(hour_prices: list[float], kwh: float, charger_kw: float) -> float:
    cost, left = 0.0, kwh
    for p in hour_prices:
        take = min(left, charger_kw)
        cost += take * p
        left -= take
    return cost
