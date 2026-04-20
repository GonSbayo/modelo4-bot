"""
Claude Agent — Decide si entrar o no en cada setup del Modelo 4
Recibe el contexto completo del setup y devuelve decision estructurada
"""
import json
import logging
import os
import anthropic

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

SYSTEM_PROMPT = """Eres un bot de trading experto en el Modelo 4 — estrategia ICT/Smart Money Concepts para futuros NQ/MNQ.

Tu única función es analizar setups candidatos y decidir si entrar o no, siguiendo el checklist exacto del Modelo 4.

SETUPS VÁLIDOS:
1. REVY (80% win rate): vela bajista seguida de vela alcista que barre liquidez abajo ($$$ confirmado), DOL arriba. Solo válido entre 9:30-15:00 ET.
2. 10AM Continuation: dos velas alcistas/bajistas consecutivas. SOLO válido entre 9:55-10:05 ET exactamente.
3. HPC (High Prob. Continuation): similar a REVY pero válido hasta las 14:00 ET.

FILTROS DE INVALIDACIÓN (si cualquiera aplica → SKIP):
- H4 va en dirección contraria al setup → SKIP o HALF_SIZE
- Wick ratio malo (superior/inferior > 0.6 en setup alcista) → SKIP
- Día NFP (primer viernes del mes) con REVY → SKIP
- Hay BSL/SSL sin barrer entre precio y DOL → SKIP (no tienes esa info, evalúa por contexto)
- HPC después de las 14:00 ET → SKIP
- Setup de 10AM fuera de ventana 9:55-10:05 ET → SKIP

CONFLUENCIAS QUE FAVORECEN ENTRAR:
- FVG presente en zona de entrada → más confianza
- H4 alineado con dirección del setup → más confianza
- Wick ratio pequeño (< 0.3) → alta probabilidad
- Setup es REVY → mayor peso (80% WR)

GESTIÓN:
- Entrada siempre en nivel 0.3 del Fibonacci (ya calculado)
- SL siempre en 0.618 del Fibonacci (ya calculado)
- TP en el DOL (ya calculado)
- Mueve SL a BE cuando precio toca el DOL

IMPORTANTE: Responde SOLO con JSON válido, sin texto adicional, sin markdown.
Formato exacto:
{
  "decision": "ENTER" | "SKIP" | "HALF_SIZE",
  "confidence": 0-100,
  "reason": "explicación breve en español (1-2 frases)",
  "entry_price": precio_exacto_0.3_fib,
  "sl": precio_stop_loss,
  "tp": precio_take_profit
}"""


class ClaudeAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    async def analyze(self, setup: dict) -> dict:
        """
        Analiza el setup y devuelve decisión de trading.
        """
        direction = setup["direction"]
        setup_type = setup["type"]
        t = setup["time_et"]
        h = t // 100
        m = t % 100

        user_message = f"""Analiza este setup del Modelo 4:

TIPO: {setup_type} {direction}
HORA ET: {h:02d}:{m:02d}

VELA ANTERIOR (v1):
- Open: {setup['v1']['open']:.2f}
- High: {setup['v1']['high']:.2f}
- Low:  {setup['v1']['low']:.2f}
- Close:{setup['v1']['close']:.2f}
- Dirección: {'BAJISTA' if setup['v1']['close'] < setup['v1']['open'] else 'ALCISTA'}

VELA ACTUAL (v2, recién cerrada):
- Open: {setup['v2']['open']:.2f}
- High: {setup['v2']['high']:.2f}
- Low:  {setup['v2']['low']:.2f}
- Close:{setup['v2']['close']:.2f}
- Dirección: {'ALCISTA' if setup['v2']['close'] > setup['v2']['open'] else 'BAJISTA'}

NIVELES CALCULADOS:
- DOL (objetivo): {setup['dol']:.2f}
- $$$ (liquidez barrida): {setup['sss']:.2f}
- Rango: {setup['range']:.2f} puntos
- Entrada (0.3 Fib): {setup['entry_036']:.2f}
- Stop Loss (0.618 Fib): {setup['sl']:.2f}
- Take Profit (DOL): {setup['tp']:.2f}
- RR potencial: {abs(setup['tp'] - setup['entry_036']) / abs(setup['entry_036'] - setup['sl']):.2f}:1

CONTEXTO:
- H4 tendencia: {setup.get('h4_trend', 'DESCONOCIDA')}
- FVG presente: {'SÍ' if setup.get('fvg') else 'NO'}
- Wick ratio: {setup.get('wick_ratio', 'N/A')}
- Día NFP: {'SÍ — no operar REVY' if setup.get('nfp_day') else 'NO'}

¿Entras o no? Recuerda: sigue el checklist del Modelo 4 estrictamente."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )

            raw = response.content[0].text.strip()
            log.info("Claude raw response: %s", raw)

            # Limpiar posibles backticks
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            decision = json.loads(raw)

            # Validación básica
            if decision.get("decision") not in ("ENTER", "SKIP", "HALF_SIZE"):
                decision["decision"] = "SKIP"
                decision["reason"] = "Respuesta inválida de IA — skip por seguridad"

            return decision

        except json.JSONDecodeError as e:
            log.error("Error parseando JSON de Claude: %s | Raw: %s", e, raw)
            return {
                "decision": "SKIP",
                "confidence": 0,
                "reason": "Error en respuesta de IA — skip por seguridad",
                "entry_price": setup["entry_036"],
                "sl": setup["sl"],
                "tp": setup["tp"],
            }
        except Exception as e:
            log.error("Error llamando a Claude: %s", e)
            return {
                "decision": "SKIP",
                "confidence": 0,
                "reason": f"Error de conexión con IA: {e}",
                "entry_price": setup["entry_036"],
                "sl": setup["sl"],
                "tp": setup["tp"],
            }
