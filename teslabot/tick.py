"""Control horario (GitHub Actions, cada hora en el minuto 55).

Mira la carga programada: con Wallbox configurado enciende/pausa el cargador; sin él, te manda avisos
de "conecta" y "desconecta" por Telegram.
"""
from datetime import datetime, timedelta

import httpx

from . import car, charger, core, store
from . import config as cfg_mod
from .daily import send


def main():
    cfg, data = core.load_all(cfg_mod.load())
    plan = data.get("plan")
    if not plan:
        return
    now = core.now()
    hours = core.plan_hours(plan)
    deadline = datetime.fromisoformat(plan["dl"])
    target = (now + timedelta(minutes=10)).replace(minute=0, second=0, microsecond=0)  # hora que empieza en breve
    sent = set(plan.get("sent", []))
    msgs = []

    if now > deadline + timedelta(hours=1):
        data.pop("plan")
        store.save(cfg.telegram_token, cfg.chat_id, data)
        return

    soc = None
    try:
        st = car.status()
        soc = st["soc"] if st else None
    except httpx.HTTPError:
        pass
    done = soc is not None and soc >= plan["tgt"]

    on = target in hours and not done
    if charger.configured():
        try:
            charger.set_charging(on)
            key = f"w{target:%d%H}{int(on)}"
            if key not in sent:
                msgs.append("▶️ Cargador encendido: toca cargar." if on else "⏸ Cargador en pausa.")
                sent.add(key)
        except Exception as e:  # sin red/credenciales mal: avisar una vez
            if "err" not in sent:
                msgs.append(f"⚠️ No pude controlar el Wallbox: {e}")
                sent.add("err")
    else:
        starts = target in hours and (target - timedelta(hours=1)) not in hours
        ends = target not in hours and (target - timedelta(hours=1)) in hours
        if starts and f"s{target:%d%H}" not in sent:
            msgs.append(f"🔌 Conecta el coche: a las {target:%H:%M} empieza tu tramo barato de carga.")
            sent.add(f"s{target:%d%H}")
        if ends and f"e{target:%d%H}" not in sent:
            msgs.append("⏹ Ya puedes desconectar: terminó el tramo de carga previsto.")
            sent.add(f"e{target:%d%H}")

    if msgs:
        for m in msgs:
            send(cfg, m)
        plan["sent"] = sorted(sent)
        store.update(cfg.telegram_token, cfg.chat_id, lambda d: d.__setitem__("plan", plan))


if __name__ == "__main__":
    main()
