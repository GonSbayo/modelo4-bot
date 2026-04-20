"""
Data client — usa yfinance para obtener velas de NQ/MNQ
"""
import logging
import os
import asyncio
from datetime import datetime

log = logging.getLogger(__name__)

DATA_MODE   = os.environ.get("DATA_MODE", "yfinance")
GATEWAY_URL = os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000")
ACCOUNT     = os.environ.get("IBKR_ACCOUNT", "DUM374430")

# NQ=F funciona mejor que MNQ=F en yfinance
YF_TICKER = {"MNQ": "NQ=F", "NQ": "NQ=F"}


class IBKRClient:

    async def get_candles(self, symbol, exchange, timeframe, count=10):
        return await self._yf(symbol, timeframe, count)

    async def _yf(self, symbol, timeframe, count):
        try:
            import yfinance as yf

            ticker   = YF_TICKER.get(symbol, "NQ=F")
            interval = {"1h": "1h", "4h": "1h", "1d": "1d"}.get(timeframe, "1h")
            period   = "30d"  # periodo amplio para asegurar datos

            def fetch():
                t = yf.Ticker(ticker)
                df = t.history(period=period, interval=interval, auto_adjust=True)
                return df

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, fetch)

            if data is None or data.empty:
                log.warning("yfinance sin datos para %s (ticker: %s)", symbol, ticker)
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

            result = candles[-count:] if len(candles) >= count else candles
            log.info("yfinance OK: %d velas %s %s (ultimo: %s close: %.2f)",
                     len(result), symbol, timeframe,
                     result[-1]["time"] if result else "N/A",
                     result[-1]["close"] if result else 0)
            return result

        except ImportError:
            log.error("yfinance no instalado — añade a requirements.txt")
            return []
        except Exception as e:
            log.error("Error yfinance %s: %s", symbol, e, exc_info=True)
            return []

    def _to_4h(self, c1h):
        out, buf = [], []
        for c in c1h:
            buf.append(c)
            if len(buf) == 4:
                out.append({
                    "time":   buf[0]["time"],
                    "open":   buf[0]["open"],
                    "high":   max(x["high"] for x in buf),
                    "low":    min(x["low"]  for x in buf),
                    "close":  buf[-1]["close"],
                    "volume": sum(x["volume"] for x in buf),
                })
                buf = []
        return out

    async def place_limit_order(self, symbol, exchange, side, qty,
                                price, sl, tp, account):
        oid = f"SIM-{datetime.now().strftime('%H%M%S')}"
        log.info("🔵 ORDEN SIMULADA | %s %dx %s @ %.2f | SL:%.2f | TP:%.2f | ID:%s",
                 side, qty, symbol, price, sl, tp, oid)
        return oid

    async def keepalive(self):
        pass
