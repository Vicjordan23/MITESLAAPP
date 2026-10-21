"""Control del Wallbox vía la nube de myWallbox (librería `wallbox`). Sin credenciales → desactivado.

Pendiente de verificar con el cargador real.
"""
import os


def configured() -> bool:
    return bool(os.getenv("WALLBOX_USER") and os.getenv("WALLBOX_PASSWORD"))


def _client():
    from wallbox import Wallbox
    w = Wallbox(os.environ["WALLBOX_USER"], os.environ["WALLBOX_PASSWORD"], requestGetTimeout=20)
    w.authenticate()
    return w


def _id(w) -> str:
    if os.getenv("WALLBOX_ID"):
        return os.environ["WALLBOX_ID"]
    groups = w.getChargersList()
    return str(groups[0])


def status() -> dict:
    w = _client()
    s = w.getChargerStatus(_id(w))
    return {"estado": s.get("status_description"), "potencia_kw": s.get("charging_power"),
            "energia_kwh": s.get("added_energy"), "corriente_max_a": s.get("max_charging_current")}


def set_charging(on: bool) -> None:
    w = _client()
    cid = _id(w)
    (w.resumeChargingSession if on else w.pauseChargingSession)(cid)
