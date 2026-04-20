"""
Data client — usa yfinance para obtener velas de MNQ
mientras se configura el IBKR gateway.
"""
import logging
import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

DATA_MODE   = os.environ.get("DATA_MODE", "yfinance")
GATEWAY_URL = os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000")
ACCOUNT     = os.environ.get("IBKR_ACCOUNT", "DUM374430")

CONID_MAP = {"MNQ": 495512552, "NQ": 371717522}
YF_TICKER = {"MNQ": "MNQ=F", "NQ": "NQ=F"}


class IBKRClient:

    async def get_candles(self, symbol, exchange, timeframe, count=10):
        return await self._yf(symbol, timeframe, count)

    async def _yf(self, symbol, timeframe, count):
        try:
            import yfinance as yf
            ticker = YF_TICKER.get(symbol, f"{symbol}=F")
            interval = {"1h": "1h", "4h": "1h", "1d": "1d"}.get(timeframe, "1h")
            period   = {"1h": "5d", "4h": "20d", "1d": "60d"}.get(timeframe, "5d")

            def fetch():
                return yf.download(ticker, period=period, interval=interval,
                                   progress=False, auto_adjust=True)

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, fetch)

            if data is None or data.empty:
                log.warning("yfinance sin datos para %s", ticker)
                return []

            candles = []
            for ts, row in data.iterrows():
                try:
                    candles.append({
                        "time":   str(ts),
                        "open":   float(row["Open"]),
                        "high":   float(row["High"]),
                        "low":    float(row["Low"]),
                        "close":  float(row["Close"]),
                        "volume": int(row.get("Volume", 0)),
                    })
                except Exception:
                    continue

            if timeframe == "4h":
                candles = self._to_4h(candles)

            result = candles[-count:]
            log.info("yfinance: %d velas %s %s", len(result), symbol, timeframe)
            return result

        except ImportError:
            log.error("yfinance no instalado")
            return []
        except Exception as e:
            log.error("Error yfinance: %s", e)
            return []

    def _to_4h(self, c1h):
        out, buf = [], []
        for c in c1h:
            buf.append(c)
            if len(buf) == 4:
                out.append({"time": buf[0]["time"], "open": buf[0]["open"],
                            "high": max(x["high"] for x in buf),
                            "low":  min(x["low"]  for x in buf),
                            "close": buf[-1]["close"],
                            "volume": sum(x["volume"] for x in buf)})
                buf = []
        return out

    async def place_limit_order(self, symbol, exchange, side, qty,
                                price, sl, tp, account):
        oid = f"SIM-{datetime.now().strftime('%H%M%S')}"
        log.info("🔵 ORDEN SIMULADA | %s %dx %s @ %.2f SL:%.2f TP:%.2f ID:%s",
                 side, qty, symbol, price, sl, tp, oid)
        return oid

    async def keepalive(self):
        pass
