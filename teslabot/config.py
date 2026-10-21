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
    webhook_secret: str = ""
    contracted_kw: float = 4.4
    house_kw: float = 1.0

    @property
    def car_kw(self) -> float:
        """Potencia real para el coche: lo que permite el cargador y lo que sobra de la contratada."""
        return max(min(self.charger_kw, self.contracted_kw - self.house_kw), 0.1)


def load() -> Config:
    return Config(
        telegram_token=os.environ["TELEGRAM_TOKEN"],
        chat_id=int(os.environ["TELEGRAM_CHAT_ID"]),
        esios_token=os.getenv("ESIOS_TOKEN", ""),
        battery_kwh=float(os.getenv("BATTERY_KWH", "60")),
        charger_kw=float(os.getenv("CHARGER_KW", "7.4")),
        efficiency=float(os.getenv("CHARGE_EFFICIENCY", "0.9")),
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        contracted_kw=float(os.getenv("CONTRACTED_KW", "4.4")),
        house_kw=float(os.getenv("HOUSE_KW", "1.0")),
    )
