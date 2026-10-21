"""Precios PVPC horarios (€/kWh) desde la API oficial de ESIOS (Red Eléctrica)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import TZ

ESIOS_URL = "https://api.esios.ree.es/indicators/1001"  # PVPC 2.0TD
GEO_PENINSULA = 8741


def fetch_prices(token: str, day: date, days: int = 2) -> dict[datetime, float]:
    """Devuelve {inicio_de_hora (tz Madrid): €/kWh} desde `day` durante `days` días.

    El precio del día siguiente aparece a partir de las ~20:30.
    """
    tz = ZoneInfo(TZ)
    start = datetime.combine(day, time.min, tz)
    end = start + timedelta(days=days) - timedelta(seconds=1)
    r = httpx.get(
        ESIOS_URL,
        params={"start_date": start.isoformat(), "end_date": end.isoformat(), "geo_ids[]": GEO_PENINSULA},
        headers={"x-api-key": token, "Accept": "application/json; application/vnd.esios-api-v1+json"},
        timeout=20,
    )
    r.raise_for_status()
    out = {}
    for v in r.json()["indicator"]["values"]:
        if v.get("geo_id") != GEO_PENINSULA:
            continue
        out[datetime.fromisoformat(v["datetime"]).astimezone(tz)] = v["value"] / 1000  # €/MWh -> €/kWh
    return out
