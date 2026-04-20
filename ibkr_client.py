"""
IBKR Client Portal Web API client
Conecta con el gateway que corre en Docker en el mismo servicio de Railway
"""
import asyncio
import logging
import os
import aiohttp

log = logging.getLogger(__name__)

GATEWAY_URL = os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000")
ACCOUNT     = os.environ.get("IBKR_ACCOUNT", "DUM374430")

# Mapa de barSize para IBKR historical data
TIMEFRAME_MAP = {
    "1h":  "1 hour",
    "4h":  "4 hours",
    "1d":  "1 day",
}

# Contract IDs de CME para futuros (conid)
# MNQ continuo
CONID_MAP = {
    "MNQ": 495512552,   # MNQ continuo en IBKR — verificar con /trsrv/futures
}


class IBKRClient:
    def __init__(self):
        self.base = GATEWAY_URL
        self.session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            # SSL=False porque el gateway usa certificado autofirmado
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    async def _get(self, path: str, params: dict = None) -> dict | list:
        session = await self._get_session()
        url = f"{self.base}/v1/api{path}"
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, data: dict = None) -> dict | list:
        session = await self._get_session()
        url = f"{self.base}/v1/api{path}"
        async with session.post(url, json=data) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_candles(self, symbol: str, exchange: str, timeframe: str, count: int = 10) -> list[dict]:
        """Obtiene velas históricas del símbolo."""
        conid = CONID_MAP.get(symbol)
        if not conid:
            raise ValueError(f"Symbol {symbol} no encontrado en CONID_MAP")

        bar_size = TIMEFRAME_MAP.get(timeframe, "1 hour")
        # IBKR period para obtener suficientes velas
        period_map = {"1 hour": f"{max(count, 10)}h", "4 hours": f"{max(count*4, 20)}h", "1 day": f"{max(count, 10)}d"}
        period = period_map.get(bar_size, "10h")

        try:
            data = await self._get(
                f"/iserver/marketdata/history",
                params={
                    "conid": conid,
                    "bar": bar_size,
                    "period": period,
                    "outsideRth": False,
                }
            )
            candles = []
            for bar in data.get("data", []):
                candles.append({
                    "time":  bar.get("t"),
                    "open":  float(bar.get("o", 0)),
                    "high":  float(bar.get("h", 0)),
                    "low":   float(bar.get("l", 0)),
                    "close": float(bar.get("c", 0)),
                    "volume":int(bar.get("v", 0)),
                })
            return candles[-count:]
        except Exception as e:
            log.error("Error obteniendo velas: %s", e)
            return []

    async def get_conid(self, symbol: str) -> int:
        """Busca el conid del contrato continuo de futuros."""
        try:
            data = await self._get(f"/trsrv/futures", params={"symbols": symbol})
            contracts = data.get(symbol, [])
            # Buscar contrato más cercano (menor tiempo hasta expiración)
            if contracts:
                return contracts[0].get("conid")
        except Exception as e:
            log.error("Error buscando conid: %s", e)
        return CONID_MAP.get(symbol)

    async def place_limit_order(
        self,
        symbol: str,
        exchange: str,
        side: str,        # "BUY" o "SELL"
        qty: int,
        price: float,
        sl: float,
        tp: float,
        account: str,
    ) -> str:
        """
        Coloca una orden límite con bracket (SL + TP) en la cuenta de paper.
        Retorna el order ID.
        """
        conid = CONID_MAP.get(symbol)
        if not conid:
            raise ValueError(f"Symbol {symbol} no encontrado")

        # Redondear precio al tick de MNQ (0.25)
        def round_tick(p: float) -> float:
            return round(round(p / 0.25) * 0.25, 2)

        price_r = round_tick(price)
        sl_r    = round_tick(sl)
        tp_r    = round_tick(tp)

        order_payload = {
            "acctId": account,
            "conid": conid,
            "secType": f"{conid}:FUT",
            "orderType": "LMT",
            "side": side,
            "quantity": qty,
            "price": price_r,
            "tif": "GTC",           # Good Till Cancelled
            "outsideRth": False,
        }

        try:
            resp = await self._post(f"/iserver/account/{account}/orders", {
                "orders": [order_payload]
            })
            order_id = resp[0].get("order_id", "unknown") if resp else "unknown"
            log.info("Orden enviada. Response: %s", resp)

            # Si hay confirmación pendiente (IBKR a veces pide confirm)
            if isinstance(resp, list) and resp and "messageIds" in resp[0]:
                confirm_id = resp[0]["messageIds"][0]
                await self._post(f"/iserver/reply/{confirm_id}", {"confirmed": True})
                log.info("Confirmación enviada para order %s", confirm_id)

            return str(order_id)
        except Exception as e:
            log.error("Error colocando orden: %s", e)
            raise

    async def get_positions(self, account: str) -> list[dict]:
        """Obtiene posiciones abiertas."""
        try:
            data = await self._get(f"/portfolio/{account}/positions/0")
            return data if isinstance(data, list) else []
        except Exception as e:
            log.error("Error obteniendo posiciones: %s", e)
            return []

    async def keepalive(self):
        """Mantiene la sesión del gateway activa (llamar cada ~60s)."""
        try:
            await self._post("/tickle")
        except Exception as e:
            log.warning("Keepalive falló: %s", e)
