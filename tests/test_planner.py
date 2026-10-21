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


def test_best_window():
    from teslabot.planner import best_window
    start, avg = best_window(prices(), D, 2)
    assert start == D + timedelta(hours=4) and round(avg, 2) == 0.05
    assert best_window(prices(), D, 50) is None


def test_tax_factor_matches_invoice():
    from teslabot.config import TAX_FACTOR
    # factura: base 35.33 -> IEE 1.81; IVA sobre (35.33+1.81+0.80)=37.94 -> 7.97
    assert abs(35.33 * 0.0511269632 - 1.81) < 0.01
    assert abs(37.94 * 0.21 - 7.97) < 0.01
    assert abs(TAX_FACTOR - 1.2709) < 0.001


def test_fmt_hours_with_prices_and_table():
    from teslabot.core import day_table, fmt_hours
    pr = prices()
    out = fmt_hours([D + timedelta(hours=4), D + timedelta(hours=5)], D, pr)
    assert out.count("€/kWh") == 2 and "0.050" in out
    assert "🟢" in day_table(pr, D.date(), D)
