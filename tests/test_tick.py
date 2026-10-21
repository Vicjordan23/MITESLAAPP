import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from teslabot import core, store, tick

TZ = ZoneInfo("Europe/Madrid")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    mem, sent = {}, []
    monkeypatch.setattr(store, "load", lambda t, i: json.loads(json.dumps(mem)))
    monkeypatch.setattr(store, "save", lambda t, i, d: (mem.clear(), mem.update(json.loads(json.dumps(d)))))
    monkeypatch.setattr(tick, "send", lambda cfg, text: sent.append(text))
    monkeypatch.setattr(tick.car, "status", lambda: None)
    return mem, sent


def plan_for(hours, dl):
    return {"cur": 30, "tgt": 80, "dl": dl.isoformat(), "hours": [h.isoformat() for h in hours],
            "kwh": 30, "cost": 3, "asap": 4, "prov": False, "sent": []}


def run_at(monkeypatch, when):
    monkeypatch.setattr(core, "now", lambda: when)
    tick.main()


def test_connect_and_disconnect_reminders(env, monkeypatch):
    mem, sent = env
    h = datetime(2026, 12, 1, 2, 0, tzinfo=TZ)
    mem["plan"] = plan_for([h, h + timedelta(hours=1)], h + timedelta(hours=6))
    run_at(monkeypatch, h - timedelta(minutes=5))          # 01:55 → conecta
    assert len(sent) == 1 and "Conecta" in sent[0]
    run_at(monkeypatch, h - timedelta(minutes=5))          # repetido: no vuelve a avisar
    assert len(sent) == 1
    run_at(monkeypatch, h + timedelta(hours=1, minutes=55))  # 03:55 → siguiente hora ya no está → desconecta
    assert len(sent) == 2 and "desconectar" in sent[1]


def test_plan_cleared_after_deadline(env, monkeypatch):
    mem, sent = env
    h = datetime(2026, 12, 1, 2, 0, tzinfo=TZ)
    mem["plan"] = plan_for([h], h + timedelta(hours=1))
    run_at(monkeypatch, h + timedelta(hours=5))
    assert "plan" not in mem and not sent
