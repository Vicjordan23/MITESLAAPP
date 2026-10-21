from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from teslabot.planner import plan_charge

TZ = ZoneInfo("Europe/Madrid")
D = datetime(2026, 12, 1, 22, 0, tzinfo=TZ)


def prices():
    # 22h..07h, la franja 02-05h es la más barata
    return {D + timedelta(hours=i): (0.05 if 4 <= i < 7 else 0.20) for i in range(10)}


def test_picks_cheapest_hours():
    # 30%->80% de 60 kWh con eficiencia 1 = 30 kWh; 10 kW => 3 horas
    plan = plan_charge(prices(), D, D + timedelta(hours=9), 30, 80, 60, 10, 1.0)
    assert plan.feasible
    assert plan.hours == [D + timedelta(hours=i) for i in (4, 5, 6)]
    assert round(plan.cost, 2) == 1.5


def test_deadline_respected_and_infeasible():
    plan = plan_charge(prices(), D, D + timedelta(hours=2), 0, 100, 60, 10, 1.0)
    assert not plan.feasible and len(plan.hours) == 2


def test_already_charged():
    plan = plan_charge(prices(), D, D + timedelta(hours=9), 80, 80, 60, 10, 1.0)
    assert plan.hours == [] and plan.feasible


def test_coverage_and_asap():
    plan = plan_charge(prices(), D, D + timedelta(hours=20), 30, 80, 60, 10, 1.0)
    assert not plan.covered  # faltan precios hasta la hora límite
    plan = plan_charge(prices(), D, D + timedelta(hours=9), 30, 80, 60, 10, 1.0)
    assert plan.covered and plan.cost_asap > plan.cost
