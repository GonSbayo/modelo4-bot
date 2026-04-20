"""
Telegram Notifier — Envía alertas del bot a tu chat de Telegram
"""
import logging
import os
import aiohttp

log = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


class TelegramNotifier:
    def __init__(self):
        self.token   = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            log.warning("Telegram no configurado — las notificaciones están desactivadas")

    async def send(self, message: str) -> bool:
        if not self.enabled:
            log.info("[TELEGRAM DESACTIVADO] %s", message)
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id":    self.chat_id,
            "text":       message,
            "parse_mode": "Markdown",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        text = await resp.text()
                        log.error("Telegram error %s: %s", resp.status, text)
                        return False
        except Exception as e:
            log.error("Error enviando Telegram: %s", e)
            return False
