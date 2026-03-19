# ============================================================
# Claude AI-powered natural language command parser
# ============================================================
import json
import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger('nlp_commands')


# ── System prompt that teaches Claude about the bot platform ─
NLP_SYSTEM_PROMPT = """
You are the command parser for an automated forex trading bot platform.

Your job is to parse natural language commands from traders and convert
them into structured JSON that the trading platform can execute.

AVAILABLE COMMAND TYPES AND THEIR JSON SCHEMAS:

1. start_bot       → {"action": "start_bot", "bot_id": "<uuid or null for all>"}
2. stop_bot        → {"action": "stop_bot", "bot_id": "<uuid or null for all>"}
3. pause_bot       → {"action": "pause_bot", "bot_id": "<uuid or null for all>"}
4. resume_bot      → {"action": "resume_bot", "bot_id": "<uuid or null for all>"}

5. set_risk        → {
     "action": "set_risk",
     "bot_id": "<uuid or null>",
     "risk_percent": <float 0.01-10 or null>,
     "stop_loss_pips": <float or null>,
     "take_profit_pips": <float or null>,
     "max_trades_per_day": <int or null>,
     "max_open_trades": <int or null>,
     "max_drawdown_percent": <float or null>,
     "trailing_stop_enabled": <bool or null>,
     "trailing_stop_pips": <float or null>,
     "use_risk_reward": <bool or null>,
     "risk_reward_ratio": <float or null>
   }

6. set_pairs       → {
     "action": "set_pairs",
     "bot_id": "<uuid or null>",
     "symbols": ["EUR_USD", "GBP_USD", ...]
   }
   NOTE: Always convert pair formats to underscore: EUR/USD → EUR_USD

7. set_timeframe   → {
     "action": "set_timeframe",
     "bot_id": "<uuid or null>",
     "timeframe": "M1|M5|M15|M30|H1|H4|D1|W1"
   }

8. set_direction   → {
     "action": "set_direction",
     "bot_id": "<uuid or null>",
     "allow_buy": <bool>,
     "allow_sell": <bool>
   }

9. open_trade      → {
     "action": "open_trade",
     "bot_id": "<uuid>",
     "symbol": "EUR_USD",
     "order_type": "buy|sell",
     "lot_size": <float or null>,
     "stop_loss_pips": <float or null>,
     "take_profit_pips": <float or null>
   }

10. close_trade    → {
      "action": "close_trade",
      "bot_id": "<uuid or null>",
      "trade_id": "<uuid or null>",
      "symbol": "<string or null>",
      "close_all": <bool>
    }

11. run_backtest   → {
      "action": "run_backtest",
      "bot_id": "<uuid>",
      "symbol": "EUR_USD",
      "timeframe": "H1",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "initial_balance": <float or null>
    }

12. get_status     → {"action": "get_status", "bot_id": "<uuid or null>"}

13. set_strategy   → {
      "action": "set_strategy",
      "bot_id": "<uuid>",
      "strategy_type": "ma_crossover|rsi_reversal|breakout|mean_reversion",
      "parameters": {}
    }

14. unknown        → {"action": "unknown", "reason": "<why you couldn't parse it>"}

RULES:
- Always respond with ONLY valid JSON. No preamble, no explanation.
- If a bot_id is mentioned or implied by context, include it. Otherwise null.
- Normalise all forex pair formats to UPPER_UNDERSCORE (EUR/USD → EUR_USD)
- If the command is ambiguous but you can make a reasonable inference, do so.
- For multi-action commands (e.g. "set risk to 1% AND only trade EUR/USD"),
  return an array of action objects: [{"action": "set_risk", ...}, {"action": "set_pairs", ...}]
- confidence: add a "confidence" field (0.0-1.0) to every object
- explanation: add a brief "explanation" field describing what you understood

EXAMPLES:
Input:  "Set stop loss to 30 pips"
Output: {"action": "set_risk", "bot_id": null, "stop_loss_pips": 30, "confidence": 0.95, "explanation": "Setting stop loss to 30 pips on all bots"}

Input:  "Only trade EUR/USD and GBP/USD going long"
Output: [
  {"action": "set_pairs", "bot_id": null, "symbols": ["EUR_USD", "GBP_USD"], "confidence": 0.95, "explanation": "Restricting pairs to EUR/USD and GBP/USD"},
  {"action": "set_direction", "bot_id": null, "allow_buy": true, "allow_sell": false, "confidence": 0.9, "explanation": "Only allowing buy (long) trades"}
]

Input:  "Stop all bots now"
Output: {"action": "stop_bot", "bot_id": null, "confidence": 1.0, "explanation": "Stopping all running bots immediately"}

Input:  "Use 2% risk with a 2:1 reward ratio"
Output: {"action": "set_risk", "bot_id": null, "risk_percent": 2.0, "use_risk_reward": true, "risk_reward_ratio": 2.0, "confidence": 0.95, "explanation": "Setting 2% risk per trade with 2:1 reward:risk ratio"}
"""


class NLPCommandParser:
    """
    Uses Claude (Anthropic API) to parse natural language trading
    commands into structured JSON actions.

    Falls back to rule-based parsing if the API is unavailable.
    """

    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model   = getattr(settings, 'NLP_MODEL', 'claude-3-5-sonnet-20241022')

    def parse(self, raw_command: str, context: dict = None) -> dict:
        """
        Parse a raw command string into structured intent.

        context: optional dict with bot info to help resolve references
                 e.g. {'bot_id': '...', 'bot_name': 'My EUR Bot', ...}

        Returns:
            {
              'actions':     [list of parsed action dicts],
              'raw_response': str,
              'model_used':   str,
              'tokens_used':  int,
              'success':      bool,
              'error':        str or None,
            }
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set — using rule-based fallback")
            return self._rule_based_parse(raw_command)

        try:
            return self._parse_with_claude(raw_command, context or {})
        except Exception as e:
            logger.error(f"Claude parse failed: {e} — falling back to rule-based")
            return self._rule_based_parse(raw_command)

    def _parse_with_claude(self, raw_command: str, context: dict) -> dict:
        """Call Anthropic API to parse the command."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        # Build user message with optional context
        user_content = raw_command
        if context:
            ctx_str = json.dumps(context, indent=2)
            user_content = (
                f"CONTEXT (active bot info):\n{ctx_str}\n\n"
                f"COMMAND: {raw_command}"
            )

        response = client.messages.create(
            model      = self.model,
            max_tokens = 1000,
            system     = NLP_SYSTEM_PROMPT,
            messages   = [
                {'role': 'user', 'content': user_content}
            ],
        )

        raw_text    = response.content[0].text.strip()
        tokens_used = response.usage.input_tokens + response.usage.output_tokens

        logger.info(
            f"Claude parsed: '{raw_command[:60]}' → {raw_text[:100]} "
            f"(tokens={tokens_used})"
        )

        # Parse the JSON response
        actions = self._extract_actions(raw_text)

        return {
            'actions':      actions,
            'raw_response': raw_text,
            'model_used':   self.model,
            'tokens_used':  tokens_used,
            'success':      True,
            'error':        None,
        }

    def _extract_actions(self, raw_text: str) -> list:
        """Extract and normalise action list from Claude's JSON response."""
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response if surrounded by text
            import re
            match = re.search(r'(\[.*\]|\{.*\})', raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except json.JSONDecodeError:
                    return [{'action': 'unknown',
                             'reason': f'Could not parse response: {raw_text[:200]}',
                             'confidence': 0.0}]
            else:
                return [{'action': 'unknown',
                         'reason': 'No JSON found in response',
                         'confidence': 0.0}]

        # Normalise to always be a list
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return parsed
        return [{'action': 'unknown', 'reason': 'Unexpected response format',
                 'confidence': 0.0}]

    def _rule_based_parse(self, raw_command: str) -> dict:
        """
        Simple keyword-based fallback parser.
        Used when Claude API is unavailable.
        Handles the most common commands without AI.
        """
        cmd   = raw_command.lower().strip()
        actions = []

        # ── Stop / Start / Pause / Resume ─────────────────────
        if any(w in cmd for w in ['stop all', 'stop bot', 'halt', 'shut down']):
            actions.append({'action': 'stop_bot', 'bot_id': None,
                           'confidence': 0.8, 'explanation': 'Stopping bots (rule-based)'})

        elif any(w in cmd for w in ['start bot', 'run bot', 'activate']):
            actions.append({'action': 'start_bot', 'bot_id': None,
                           'confidence': 0.8, 'explanation': 'Starting bots (rule-based)'})

        elif any(w in cmd for w in ['pause', 'suspend']):
            actions.append({'action': 'pause_bot', 'bot_id': None,
                           'confidence': 0.8, 'explanation': 'Pausing bots (rule-based)'})

        elif any(w in cmd for w in ['resume', 'continue', 'unpause']):
            actions.append({'action': 'resume_bot', 'bot_id': None,
                           'confidence': 0.8, 'explanation': 'Resuming bots (rule-based)'})

        # ── Status ────────────────────────────────────────────
        elif any(w in cmd for w in ['status', 'how is', 'what is', 'report']):
            actions.append({'action': 'get_status', 'bot_id': None,
                           'confidence': 0.8, 'explanation': 'Getting status (rule-based)'})

        # ── Risk settings ─────────────────────────────────────
        elif any(w in cmd for w in ['risk', 'stop loss', 'take profit', 'sl', 'tp']):
            risk_action = {'action': 'set_risk', 'bot_id': None, 'confidence': 0.6,
                          'explanation': 'Risk setting detected — AI needed for full parse'}

            import re
            # Extract risk percent e.g. "1.5%" or "1.5 percent"
            pct_match = re.search(r'(\d+\.?\d*)\s*%', cmd)
            if pct_match:
                risk_action['risk_percent'] = float(pct_match.group(1))

            # Extract pip values e.g. "50 pips"
            pip_match = re.findall(r'(\d+)\s*pip', cmd)
            if pip_match and 'stop loss' in cmd:
                risk_action['stop_loss_pips'] = float(pip_match[0])
            elif pip_match and 'take profit' in cmd:
                risk_action['take_profit_pips'] = float(pip_match[0])

            actions.append(risk_action)

        # ── Close all ─────────────────────────────────────────
        elif any(w in cmd for w in ['close all', 'exit all', 'close everything']):
            actions.append({'action': 'close_trade', 'bot_id': None,
                           'close_all': True, 'confidence': 0.9,
                           'explanation': 'Closing all positions (rule-based)'})

        else:
            actions.append({'action': 'unknown',
                           'reason': f'Rule-based parser could not parse: {raw_command}',
                           'confidence': 0.0})

        return {
            'actions':      actions,
            'raw_response': f'rule_based: {raw_command}',
            'model_used':   'rule_based',
            'tokens_used':  0,
            'success':      True,
            'error':        None,
        }