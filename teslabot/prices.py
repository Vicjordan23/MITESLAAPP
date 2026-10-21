"""Precios PVPC horarios (€/kWh) desde la API oficial de ESIOS (Red Eléctrica)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from .config import TZ

ESIOS_URL = "https://api.esios.ree.es/indicators/1001"  # PVPC 2.0TD
GEO_PENINSULA = 8741
REE_URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"  # pública, sin token


def _fetch_ree_public(day: date, days: int) -> dict[datetime, float]:
    tz = ZoneInfo(TZ)
    end = day + timedelta(days=days - 1)
    r = httpx.get(REE_URL, params={"start_date": f"{day}T00:00", "end_date": f"{end}T23:59", "time_trunc": "hour"},
                  headers={"Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    pvpc = next(i for i in r.json()["included"] if i["id"] == "1001")
    return {datetime.fromisoformat(v["datetime"]).astimezone(tz): v["value"] / 1000
            for v in pvpc["attributes"]["values"]}


def fetch_prices(token: str, day: date, days: int = 2) -> dict[datetime, float]:
    """Devuelve {inicio_de_hora (tz Madrid): €/kWh} desde `day` durante `days` días.

    El precio del día siguiente aparece a partir de las ~20:30.
    """
    if not token or token == "pendiente":
        return _fetch_ree_public(day, days)
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
