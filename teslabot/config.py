import os
from dataclasses import dataclass

TZ = "Europe/Madrid"


@dataclass(frozen=True)
class Config:
    telegram_token: str
    chat_id: int
    esios_token: str
    battery_kwh: float
    charger_kw: float
    efficiency: float


def load() -> Config:
    return Config(
        telegram_token=os.environ["TELEGRAM_TOKEN"],
        chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
        esios_token=os.environ["ESIOS_TOKEN"],
        battery_kwh=float(os.getenv("BATTERY_KWH", "60")),
        charger_kw=float(os.getenv("CHARGER_KW", "7.4")),
        efficiency=float(os.getenv("CHARGE_EFFICIENCY", "0.9")),
    )
