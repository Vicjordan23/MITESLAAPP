"""Estado del coche. Proveedor opcional: Tessie (https://tessie.com, de pago). Sin configurar → None.

Pendiente de verificar con un coche real (llega en diciembre).
"""
import os

import httpx


def configured() -> bool:
    return bool(os.getenv("TESSIE_TOKEN") and os.getenv("TESSIE_VIN"))


def status() -> dict | None:
    """{'soc': 42, 'charging': 'Charging', 'limit': 80, 'plugged': True} o None."""
    if not configured():
        return None
    r = httpx.get(f"https://api.tessie.com/{os.environ['TESSIE_VIN']}/state",
                  headers={"Authorization": f"Bearer {os.environ['TESSIE_TOKEN']}"}, params={"use_cache": "true"},
                  timeout=30)
    r.raise_for_status()
    cs = r.json().get("charge_state", {})
    state = cs.get("charging_state")
    return {"soc": cs.get("battery_level"), "charging": state, "limit": cs.get("charge_limit_soc"),
            "plugged": state not in (None, "Disconnected")}
