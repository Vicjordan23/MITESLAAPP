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

## Funciones
- **Ajustes desde Telegram** (⚙️): batería, cargador, potencia contratada, reserva de casa, consumo y umbrales de aviso. Se guardan en un mensaje fijado del propio chat (no lo borres ni lo desfijes), así sobreviven a reinicios de Render sin base de datos.
- **Cargas programadas** (📌): el bot las guarda y las replanifica a las 20:35 si se programaron antes de conocer los precios de mañana. Cada hora (minuto 55) `teslabot.tick` en GitHub Actions te avisa de conectar/desconectar o, si hay Wallbox configurado, lo enciende/pausa.
- **Avisos 20:35**: resumen de mañana + 🟢 día barato / 🔴 día caro según tus umbrales.
- **Estado del coche** (opcional, Tessie) y **Wallbox** (opcional, myWallbox): sin verificar con hardware real todavía.
- **Resumen mensual**: estimado a partir de las cargas programadas.

Secrets de GitHub para `control-horario`: los mismos que `aviso-diario` y, opcionalmente, `WALLBOX_USER`, `WALLBOX_PASSWORD`, `WALLBOX_ID`, `TESSIE_TOKEN`, `TESSIE_VIN`.
