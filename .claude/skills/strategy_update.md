---
name: strategy_update
description: "Modify strategy specifications with natural language intent (D10, FR73)"
triggers:
  - "try wider stops"
  - "change the timeframe"
  - "add a filter"
  - "modify strategy"
  - "update strategy"
---

# Strategy Update / Modification

Modify a strategy specification based on operator's natural language intent.

## Workflow

1. **Identify the strategy**: Ask for `strategy_slug` if not provided
2. **Interpret intent**: Translate the operator's natural language into structured modification JSON:
   - "try wider stops" → `{"modifications": [{"field": "exit_rules.stop_loss.value", "action": "set", "value": 2.0, "description": "wider stops"}]}`
   - "add a London session filter" → `{"modifications": [{"field": "entry_rules.filters", "action": "add", "value": {"type": "session", "params": {"include": ["london"]}}, "description": "London session filter"}]}`
   - "change risk to 2%" → `{"modifications": [{"field": "position_sizing.risk_percent", "action": "set", "value": 2.0, "description": "increase risk per trade"}]}`

3. **Apply**: Run the modification command:
   ```bash
   cd /c/Users/ROG/Projects/Forex\ Pipeline/src/python && python -m strategy modify <strategy_slug> --input '<json>'
   ```

4. **Report**: Display the diff summary:
   - "Modified ma-crossover-eurusd-h1: v001 → v002. Changes: [diff]. Run /strategy_review to review and confirm."

## Valid Modification Fields

- `exit_rules.stop_loss.type` / `.value` — Stop loss settings
- `exit_rules.take_profit.type` / `.value` — Take profit settings
- `exit_rules.trailing` — Trailing stop configuration
- `entry_rules.filters` — Add/remove entry filters
- `entry_rules.conditions` — Modify entry conditions
- `entry_rules.confirmation` — Modify confirmation indicators
- `position_sizing.method` / `.risk_percent` / `.max_lots` — Position sizing
- `metadata.name` / `.timeframe` — Strategy identity

## Notes

- D9 boundary: calls Python CLI directly — TODO for REST API migration
- D10 boundary: AI interpretation (this skill) is separate from deterministic modification (Python)
- Modifications always create a new version; previous version is preserved (FR12)
- New version starts as 'draft' — operator must confirm via /strategy_review
