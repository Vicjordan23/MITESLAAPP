"""Guarda datos (ajustes, plan de carga, historial) en un mensaje fijado del propio chat de Telegram.

Así sobrevive a reinicios de Render y lo puede leer también GitHub Actions, sin base de datos.
"""
import json
import logging

import httpx

log = logging.getLogger("teslabot.store")
HEADER = "🔧 Datos del bot (no borrar ni desfijar)\n"
_mem: dict = {}


def _api(token: str, method: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{token}/{method}", json=params, timeout=20)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"{method}: {data.get('description')}")
    return data["result"]


def _pinned(token: str, chat_id: int) -> dict | None:
    return _api(token, "getChat", chat_id=chat_id).get("pinned_message")


def load(token: str, chat_id: int) -> dict:
    try:
        pin = _pinned(token, chat_id)
        if pin and pin.get("text", "").startswith(HEADER):
            _mem.clear()
            _mem.update(json.loads(pin["text"][len(HEADER):]))
    except Exception:
        log.exception("no se pudo leer el mensaje fijado; uso la memoria")
    return dict(_mem)


def save(token: str, chat_id: int, data: dict) -> None:
    _mem.clear()
    _mem.update(data)
    text = HEADER + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    try:
        pin = _pinned(token, chat_id)
        if pin and pin.get("text", "").startswith(HEADER):
            if pin["text"] != text:
                _api(token, "editMessageText", chat_id=chat_id, message_id=pin["message_id"], text=text)
        else:
            m = _api(token, "sendMessage", chat_id=chat_id, text=text)
            _api(token, "pinChatMessage", chat_id=chat_id, message_id=m["message_id"], disable_notification=True)
    except Exception:
        log.exception("no se pudo guardar en Telegram; queda solo en memoria")


def update(token: str, chat_id: int, fn) -> dict:
    """Lee-modifica-escribe: `fn(data)` cambia el dict en sitio."""
    data = load(token, chat_id)
    fn(data)
    save(token, chat_id, data)
    return data
