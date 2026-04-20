# Modelo 4 Bot — ICT/SMC Trading Bot para MNQ

Bot automatizado que detecta setups del Modelo 4 (REVY, 10AM Continuation, HPC)
en futuros MNQ, usa Claude AI para decidir entradas, y ejecuta en IBKR Paper Trading.

## Stack
- **Datos + Ejecución**: IBKR Client Portal Web API (cuenta paper gratuita)
- **Detección**: Python puro (sin TradingView)
- **Decisión IA**: Claude API (claude-sonnet-4-6)
- **Notificaciones**: Telegram
- **Despliegue**: Railway (24/7 en la nube)

## Setup en Railway

### 1. Crea el repo en GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/TU_USUARIO/modelo4-bot.git
git push -u origin main
```

### 2. Despliega en Railway
1. Ve a railway.app → New Project → Deploy from GitHub
2. Selecciona el repo `modelo4-bot`
3. Railway detectará el Dockerfile automáticamente

### 3. Configura las variables de entorno en Railway
En Railway → tu proyecto → Variables, añade:
```
ANTHROPIC_API_KEY    = sk-ant-api03-...
IBKR_USERNAME        = rkkqfo114
IBKR_PASSWORD        = tu_password
IBKR_ACCOUNT         = DUM374430
TELEGRAM_TOKEN       = tu_token (opcional)
TELEGRAM_CHAT_ID     = tu_chat_id (opcional)
```

### 4. Telegram (opcional)
1. Habla con @BotFather → /newbot → guarda el token
2. Envía /start a tu bot
3. Ve a `https://api.telegram.org/bot<TOKEN>/getUpdates` → copia el `id` de `chat`

## Archivos
- `bot.py` — Loop principal, detección de setups
- `ibkr_client.py` — Cliente de la Web API de IBKR
- `claude_agent.py` — Agente IA que decide entradas
- `telegram_notifier.py` — Notificaciones
- `docker-compose.yml` — Para correr localmente
- `Dockerfile` — Para Railway

## Correr localmente (para pruebas)
```bash
cp .env.example .env
# Rellena el .env con tus credenciales
docker-compose up
```

## Lógica del bot
1. Cada 30 segundos comprueba si hay mercado abierto (9:30-15:00 ET)
2. Al cierre de cada vela H1, analiza las últimas 2 velas
3. Si detecta REVY, 10AM o HPC con los filtros correctos:
   - Envía el contexto a Claude con el prompt del Modelo 4
   - Claude devuelve ENTER / SKIP / HALF_SIZE
   - Si ENTER: coloca orden límite en el nivel 0.3 del Fibonacci
   - SL automático en 0.618, TP en el DOL
4. Notifica por Telegram cada señal y cada orden ejecutada
