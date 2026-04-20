"""
Modelo 4 Bot — Detector de setups ICT/SMC para MNQ
Conecta con IBKR Web API para datos y ejecución
Usa Claude API para decidir entradas
"""
import asyncio
import logging
import os
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from ibkr_client import IBKRClient
from claude_agent import ClaudeAgent
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# ── Configuración ─────────────────────────────────────────────
SYMBOL       = "MNQ"          # Micro E-mini Nasdaq
EXCHANGE     = "CME"
TIMEFRAME    = "1h"
ACCOUNT      = os.environ["IBKR_ACCOUNT"]   # DUM374430

# Ventanas horarias ET (hora * 100 + minutos)
WINDOW_REVY_OPEN  = 930
WINDOW_REVY_CLOSE = 1500
WINDOW_10AM_OPEN  = 955
WINDOW_10AM_CLOSE = 1005
WINDOW_HPC_CLOSE  = 1400

# Fibonacci
FIB_ENTRY = 0.300
FIB_SL    = 0.618


def et_now() -> datetime:
    return datetime.now(ET)


def et_time_int() -> int:
    n = et_now()
    return n.hour * 100 + n.minute


def is_market_hours() -> bool:
    t = et_time_int()
    return WINDOW_REVY_OPEN <= t <= WINDOW_REVY_CLOSE


def is_nfp_day() -> bool:
    """Primer viernes del mes = día NFP"""
    n = et_now()
    return n.weekday() == 4 and n.day <= 7


# ── Detección de setups ───────────────────────────────────────
def detect_setup(candles: list[dict]) -> dict | None:
    """
    Analiza las últimas 2 velas H1 y detecta REVY, 10AM o HPC.
    Retorna dict con info del setup o None si no hay setup válido.

    candles: lista de dicts con keys open, high, low, close, time
    Orden: candles[-2] = vela anterior, candles[-1] = vela actual (recién cerrada)
    """
    if len(candles) < 3:
        return None

    v1 = candles[-2]   # vela anterior
    v2 = candles[-1]   # vela actual (recién cerrada)

    t = et_time_int()

    # Propiedades básicas
    v1_bull = v1["close"] > v1["open"]
    v1_bear = v1["close"] < v1["open"]
    v2_bull = v2["close"] > v2["open"]
    v2_bear = v2["close"] < v2["open"]

    # Cuerpo mínimo 30% del rango
    def body_pct(v):
        rng = v["high"] - v["low"]
        return abs(v["close"] - v["open"]) / rng if rng > 0 else 0

    if body_pct(v1) < 0.30 or body_pct(v2) < 0.30:
        return None

    # Wick ratio (para setup alcista: mecha superior / mecha inferior)
    def wick_ratio_bull(v):
        upper = v["high"] - max(v["open"], v["close"])
        lower = min(v["open"], v["close"]) - v["low"]
        return upper / lower if lower > 0 else 999

    def wick_ratio_bear(v):
        upper = v["high"] - max(v["open"], v["close"])
        lower = min(v["open"], v["close"]) - v["low"]
        return lower / upper if upper > 0 else 999

    # FVG
    if len(candles) >= 3:
        v0 = candles[-3]
        fvg_bull = v0["high"] < v2["low"]
        fvg_bear = v0["low"]  > v2["high"]
    else:
        fvg_bull = fvg_bear = False

    setup = None

    # ── REVY ALCISTA ──────────────────────────────────────────
    if (WINDOW_REVY_OPEN <= t <= WINDOW_REVY_CLOSE
            and v1_bear and v2_bull
            and v2["low"] <= v1["low"]           # barre liquidez abajo ($$$)
            and v2["close"] > v1["open"]          # cierra sobre apertura v1
            and wick_ratio_bull(v2) <= 0.6
            and not is_nfp_day()):

        dol = v2["high"]
        sss = min(v2["low"], v1["low"])
        rng = dol - sss
        setup = {
            "type": "REVY",
            "direction": "LONG",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol - rng * FIB_ENTRY,
            "sl": dol - rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bull,
            "wick_ratio": round(wick_ratio_bull(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    # ── REVY BAJISTA ─────────────────────────────────────────
    elif (WINDOW_REVY_OPEN <= t <= WINDOW_REVY_CLOSE
            and v1_bull and v2_bear
            and v2["high"] >= v1["high"]
            and v2["close"] < v1["open"]
            and wick_ratio_bear(v2) <= 0.6
            and not is_nfp_day()):

        dol = v2["low"]
        sss = max(v2["high"], v1["high"])
        rng = sss - dol
        setup = {
            "type": "REVY",
            "direction": "SHORT",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol + rng * FIB_ENTRY,
            "sl": dol + rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bear,
            "wick_ratio": round(wick_ratio_bear(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    # ── 10AM CONTINUATION ALCISTA ────────────────────────────
    elif (WINDOW_10AM_OPEN <= t <= WINDOW_10AM_CLOSE
            and v1_bull and v2_bull
            and v2["high"] > v1["high"]
            and v2["close"] > v1["high"]
            and not is_nfp_day()):

        dol = v2["high"]
        sss = min(v2["low"], v1["low"])
        rng = dol - sss
        setup = {
            "type": "10AM",
            "direction": "LONG",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol - rng * FIB_ENTRY,
            "sl": dol - rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bull,
            "wick_ratio": round(wick_ratio_bull(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    # ── 10AM CONTINUATION BAJISTA ────────────────────────────
    elif (WINDOW_10AM_OPEN <= t <= WINDOW_10AM_CLOSE
            and v1_bear and v2_bear
            and v2["low"] < v1["low"]
            and v2["close"] < v1["low"]
            and not is_nfp_day()):

        dol = v2["low"]
        sss = max(v2["high"], v1["high"])
        rng = sss - dol
        setup = {
            "type": "10AM",
            "direction": "SHORT",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol + rng * FIB_ENTRY,
            "sl": dol + rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bear,
            "wick_ratio": round(wick_ratio_bear(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    # ── HPC ALCISTA ──────────────────────────────────────────
    elif (t < WINDOW_HPC_CLOSE
            and WINDOW_10AM_CLOSE < t          # no solapar con 10AM
            and v1_bear and v2_bull
            and v2["high"] > v1["high"]
            and v2["close"] > v1["high"]
            and not is_nfp_day()):

        dol = v2["high"]
        sss = min(v2["low"], v1["low"])
        rng = dol - sss
        setup = {
            "type": "HPC",
            "direction": "LONG",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol - rng * FIB_ENTRY,
            "sl": dol - rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bull,
            "wick_ratio": round(wick_ratio_bull(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    # ── HPC BAJISTA ──────────────────────────────────────────
    elif (t < WINDOW_HPC_CLOSE
            and WINDOW_10AM_CLOSE < t
            and v1_bull and v2_bear
            and v2["low"] < v1["low"]
            and v2["close"] < v1["low"]
            and not is_nfp_day()):

        dol = v2["low"]
        sss = max(v2["high"], v1["high"])
        rng = sss - dol
        setup = {
            "type": "HPC",
            "direction": "SHORT",
            "dol": dol,
            "sss": sss,
            "range": rng,
            "entry_036": dol + rng * FIB_ENTRY,
            "sl": dol + rng * FIB_SL,
            "tp": dol,
            "fvg": fvg_bear,
            "wick_ratio": round(wick_ratio_bear(v2), 2),
            "v1": v1,
            "v2": v2,
            "time_et": t,
        }

    return setup


# ── Loop principal ────────────────────────────────────────────
async def main():
    ibkr     = IBKRClient()
    claude   = ClaudeAgent()
    telegram = TelegramNotifier()

    log.info("🤖 Modelo 4 Bot arrancado — cuenta %s", ACCOUNT)
    await telegram.send("🤖 *Modelo 4 Bot arrancado*\nCuenta: `" + ACCOUNT + "`\nEsperando setups en MNQ...")

    last_candle_time = None

    while True:
        try:
            if not is_market_hours():
                log.info("Fuera de horario ET (%s). Esperando...", et_time_int())
                await asyncio.sleep(60)
                continue

            # Obtener últimas velas H1
            candles = await ibkr.get_candles(SYMBOL, EXCHANGE, TIMEFRAME, count=10)
            if not candles:
                await asyncio.sleep(30)
                continue

            latest = candles[-1]["time"]
            if latest == last_candle_time:
                # Misma vela, esperar cierre
                await asyncio.sleep(30)
                continue

            last_candle_time = latest
            log.info("Nueva vela H1 cerrada: %s", latest)

            # Detectar setup
            setup = detect_setup(candles)
            if not setup:
                log.info("No hay setup en esta vela.")
                await asyncio.sleep(30)
                continue

            log.info("⚡ Setup detectado: %s %s | Entry: %.2f | SL: %.2f | TP: %.2f",
                     setup["type"], setup["direction"],
                     setup["entry_036"], setup["sl"], setup["tp"])

            # Obtener H4 trend
            h4_candles = await ibkr.get_candles(SYMBOL, EXCHANGE, "4h", count=5)
            h4_trend = "BULLISH" if h4_candles and h4_candles[-1]["close"] > h4_candles[-2]["close"] else "BEARISH"

            # Enriquecer setup con H4
            setup["h4_trend"] = h4_trend

            # Claude decide
            decision = await claude.analyze(setup)
            log.info("🧠 Claude decide: %s | Confianza: %s%% | Razón: %s",
                     decision["decision"], decision["confidence"], decision["reason"])

            await telegram.send(
                f"⚡ *Setup detectado: {setup['type']} {setup['direction']}*\n"
                f"Entry: `{setup['entry_036']:.2f}` | SL: `{setup['sl']:.2f}` | TP: `{setup['tp']:.2f}`\n"
                f"H4: {h4_trend} | FVG: {'✓' if setup['fvg'] else '✗'} | Wick: {setup['wick_ratio']}\n"
                f"🧠 Claude: *{decision['decision']}* ({decision['confidence']}%)\n"
                f"_{decision['reason']}_"
            )

            if decision["decision"] in ("ENTER", "HALF_SIZE"):
                qty = 1 if decision["decision"] == "ENTER" else 1  # micro = 1 contrato mínimo
                side = "BUY" if setup["direction"] == "LONG" else "SELL"

                order_id = await ibkr.place_limit_order(
                    symbol   = SYMBOL,
                    exchange = EXCHANGE,
                    side     = side,
                    qty      = qty,
                    price    = setup["entry_036"],
                    sl       = setup["sl"],
                    tp       = setup["tp"],
                    account  = ACCOUNT,
                )
                log.info("✅ Orden colocada: %s | ID: %s", side, order_id)
                await telegram.send(
                    f"✅ *Orden colocada en DEMO*\n"
                    f"{side} {qty}x MNQ @ `{setup['entry_036']:.2f}`\n"
                    f"SL: `{setup['sl']:.2f}` | TP: `{setup['tp']:.2f}`\n"
                    f"Order ID: `{order_id}`"
                )

        except Exception as e:
            log.error("Error en loop: %s", e, exc_info=True)
            await telegram.send(f"⚠️ Error en bot: `{e}`")
            await asyncio.sleep(60)

        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
