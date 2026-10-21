import os
from dataclasses import dataclass, replace

TZ = "Europe/Madrid"
IMPUESTO_ELECTRICIDAD = 0.0511269632  # sobre energía+potencia
IVA = 0.21
TAX_FACTOR = (1 + IMPUESTO_ELECTRICIDAD) * (1 + IVA)  # precio PVPC * esto = lo que pagas por kWh (para el total futuro)

# Ajustes que se pueden cambiar desde Telegram y se guardan en el mensaje fijado (store.py)
EDITABLE = ("battery_kwh", "charger_kw", "contracted_kw", "house_kw", "kwh_per_100km", "alert_low", "alert_high", "alerts")


@dataclass
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
    kwh_per_100km: float = 15.0
    alert_low: float = 0.08    # €/kWh base: media de mañana por debajo → "día barato"
    alert_high: float = 0.18   # media por encima → "día caro"
    alerts: bool = True

    @property
    def car_kw(self) -> float:
        """Potencia real para el coche: lo que permite el cargador y lo que sobra de la contratada."""
        return max(min(self.charger_kw, self.contracted_kw - self.house_kw), 0.1)

    def with_overrides(self, saved: dict) -> "Config":
        return replace(self, **{k: type(getattr(self, k))(v) for k, v in saved.items() if k in EDITABLE})


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
        kwh_per_100km=float(os.getenv("KWH_PER_100KM", "15")),
    )
