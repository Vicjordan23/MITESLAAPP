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
    cost = 0.0
    left = kwh
    for p, _ in sorted(chosen):  # las más baratas se llenan primero
        take = min(left, charger_kw)
        cost += take * p
        left -= take
    return Plan([h for _, h in chosen], kwh, cost, len(chosen) == n_hours)
