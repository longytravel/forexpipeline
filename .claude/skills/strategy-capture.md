---
name: strategy-capture
description: "Create a new trading strategy from natural language dialogue. Use when the operator says 'create a strategy', 'new strategy', 'try a strategy', or 'define a strategy'."
---

# Strategy Capture Skill

You are helping the operator create a trading strategy specification from their natural language description.

## Your Role

You are the **AI interpretation layer** (D10 Intent Capture). You receive the operator's natural language strategy description and extract structured elements into a dict. The Python module handles normalization, validation, and specification generation deterministically.

# TODO(D9): migrate to REST API when orchestrator is available

## Flow

1. **Receive** the operator's strategy description in natural language
2. **Extract** structured elements using your understanding:
   - `pair`: Trading pair (e.g., "EURUSD", "EUR/USD")
   - `timeframe`: Chart timeframe (e.g., "H1", "1 hour", "daily")
   - `indicators`: List of indicators with type, params, and role (signal/filter/exit)
   - `entry_conditions`: List of entry condition descriptions
   - `exit_rules`: List of exit rules with type and params
   - `filters`: List of filters with type and params (session, volatility)
   - `position_sizing`: Optional sizing method and params
   - `raw_description`: The original operator text
3. **Call** the Python intent capture module with the structured dict
4. **Report** the result or handle errors

## Structured Input Format

Build a JSON dict from the operator's description:

```json
{
    "raw_description": "<original operator text>",
    "pair": "EURUSD",
    "timeframe": "H1",
    "indicators": [
        {"type": "sma_crossover", "params": {"fast_period": 20, "slow_period": 50}, "role": "signal"}
    ],
    "entry_conditions": ["SMA(20) crosses above SMA(50)"],
    "exit_rules": [
        {"type": "chandelier", "params": {"atr_period": 14, "atr_multiplier": 3.0}}
    ],
    "filters": [
        {"type": "session", "params": {"session": "london"}}
    ]
}
```

## Known Indicator Types

Map natural language to these registry types:
- "moving average", "MA", "SMA" → `sma`
- "exponential moving average", "EMA" → `ema`
- "MA crossover", "moving average crossover" → `sma_crossover`
- "EMA crossover" → `ema_crossover`
- "ATR", "average true range" → `atr`
- "Bollinger Bands" → `bollinger_bands`
- "RSI" → `rsi`
- "MACD" → `macd`
- "Stochastic" → `stochastic`
- "Supertrend" → `supertrend`
- "Donchian" → `donchian_channel`
- "ADX" → `adx`

## Known Exit Types

- "stop loss" → `stop_loss`
- "take profit" → `take_profit`
- "trailing stop" → `trailing_stop`
- "chandelier exit" → `chandelier`

## Known Filter Types

- "London session", "Asian session", etc. → `session` filter with `{"session": "<name>"}`
- "volatility filter" → `volatility` filter

## Execution

Run the Python module with the structured JSON:

```bash
cd /c/Users/ROG/Projects/Forex\ Pipeline && PYTHONPATH=src/python python -m strategy.intent_capture '<json_structured_input>'
```

Or via Python directly:

```python
import json
from pathlib import Path
from strategy.intent_capture import capture_strategy_intent

structured_input = {... extracted dict ...}
artifacts_dir = Path("artifacts/strategies")
result = capture_strategy_intent(structured_input, artifacts_dir)
```

## Success Response

Report to the operator:
- Draft spec saved: `{strategy_name} {version}`
- Path: `{saved_path}`
- Run `/strategy-review` to review and confirm

## Error Handling

If `IntentCaptureError` is raised (missing indicators or entry logic):
- Present the error message clearly
- Ask the operator to provide the missing elements
- Do NOT fabricate missing strategy-defining elements

## What This Skill Does NOT Do

- Does NOT present a full human-readable review (that is Story 2.5's `/strategy-review` responsibility)
- Does NOT set optimization parameters (Story 2.8)
- Does NOT create cost models (Story 2.6)
- Does NOT confirm/lock the specification (Story 2.5)
