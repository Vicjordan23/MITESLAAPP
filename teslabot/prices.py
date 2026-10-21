"""Precios PVPC horarios (€/kWh) desde la API oficial de ESIOS (Red Eléctrica)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import time as _time

import httpx

from .config import TAX_FACTOR, TZ

ESIOS_URL = "https://api.esios.ree.es/indicators/1001"  # PVPC 2.0TD
GEO_PENINSULA = 8741
REE_URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"  # pública, sin token


def _fetch_ree_public(day: date, days: int) -> dict[datetime, float]:
    """Un día por petición: si el día siguiente aún no está publicado la API responde error y se omite."""
    tz = ZoneInfo(TZ)
    out: dict[datetime, float] = {}
    for i in range(days):
        d = day + timedelta(days=i)
        try:
            r = httpx.get(REE_URL, params={"start_date": f"{d}T00:00", "end_date": f"{d}T23:59", "time_trunc": "hour"},
                          headers={"Accept": "application/json", "User-Agent": "miteslaapp/1.0"}, timeout=20)
            r.raise_for_status()
            pvpc = next(x for x in r.json()["included"] if x["id"] == "1001")
        except (httpx.HTTPError, StopIteration, KeyError):
            if i == 0:
                raise
            continue
        for v in pvpc["attributes"]["values"]:
            out[datetime.fromisoformat(v["datetime"]).astimezone(tz)] = v["value"] / 1000
    return out


def _fetch_prices_raw(token: str, day: date, days: int = 2) -> dict[datetime, float]:
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


def fetch_real_prices(token: str, day: date, days: int = 2) -> dict[datetime, float]:
    """Como fetch_prices pero con IVA e impuesto de electricidad: lo que de verdad pagas por kWh."""
    return {h: p * TAX_FACTOR for h, p in fetch_prices(token, day, days).items()}


_CACHE: dict = {}
_TTL = 600  # s


def fetch_prices(token: str, day: date, days: int = 2) -> dict[datetime, float]:
    """Con caché de 10 min y 3 reintentos (la API pública da algún 403/5xx suelto)."""
    key = (token, day, days)
    hit = _CACHE.get(key)
    if hit and _time.monotonic() - hit[0] < _TTL:
        return hit[1]
    last = None
    for wait in (0, 1, 3):
        _time.sleep(wait)
        try:
            data = _fetch_prices_raw(token, day, days)
            _CACHE[key] = (_time.monotonic(), data)
            return data
        except httpx.HTTPError as e:
            last = e
    if hit:  # mejor datos algo viejos que ningún dato
        return hit[1]
    raise last
