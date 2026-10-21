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

## Despliegue gratis
- **Bot (Render, plan free, webhook):** New → Blueprint → este repo (usa `render.yaml`). Rellenar las variables marcadas. Tras 15 min sin uso se duerme y Telegram lo despierta (la primera respuesta tarda ~30-60 s).
- **Aviso 20:35 (GitHub Actions):** Settings → Secrets → `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `ESIOS_TOKEN`. Prueba manual: Actions → aviso-diario → Run workflow.

## Menú del bot
`/menu` abre un menú con botones: cargar el coche (asistente paso a paso: batería actual → objetivo → día → hora), precios, horas más baratas ahora, mejor hora para electrodomésticos y ajustes.
