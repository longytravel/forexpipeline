---
name: strategy_review
description: "Review and confirm strategy specifications for pipeline use (D9, D10)"
triggers:
  - "review strategy"
  - "show strategy"
  - "what does this strategy do"
  - "confirm strategy"
  - "lock strategy"
---

# Strategy Review & Confirmation

Review a strategy specification's human-readable summary and optionally confirm it for pipeline use.

## Workflow

1. **Identify the strategy**: Ask for `strategy_slug` if not provided (e.g., "ma-crossover-eurusd-h1")
2. **Review**: Run the review command to display the human-readable summary:
   ```bash
   cd /c/Users/ROG/Projects/Forex\ Pipeline/src/python && python -m strategy review <strategy_slug> [--version v001]
   ```
3. **Display**: Show the formatted summary to the operator
4. **Ask**: "Confirm this strategy for pipeline use? (yes/no/modify)"
   - **yes** → Confirm:
     ```bash
     cd /c/Users/ROG/Projects/Forex\ Pipeline/src/python && python -m strategy confirm <strategy_slug> <version>
     ```
   - **modify** → Ask what to change, then invoke `/strategy_update`
   - **no** → Done, no action taken

## Notes

- D9 boundary: calls Python CLI directly (REST API not yet available — TODO for API migration when orchestrator lands)
- Review output is human-readable plain English, no raw spec format exposed
- Confirmation locks the spec: status → confirmed, attaches config_hash for reproducibility
- Previous versions are never overwritten (FR12 immutability)
