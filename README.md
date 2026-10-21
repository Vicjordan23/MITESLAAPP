# MITESLAAPP

Bot de Telegram que planifica la carga del Tesla en las horas más baratas del PVPC.

## Fase 1 (actual, sin coche ni cargador)
- `/precios` — precios de hoy/mañana
- `/cargar 30 80 07:30` — dice cuándo conectar para llegar al % indicado a esa hora
- Aviso diario 20:35 con las horas más baratas de mañana

## Arrancar
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # rellenar y exportar las variables
.venv/bin/python -m teslabot.bot
.venv/bin/python -m pytest
```
