from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot.config import Config
    from jobpilot.db import Database


def compute_ladder(config: "Config", db: "Database") -> dict:
    """Return ladder state for the BYO key cutover UI.

    States:
      byo           — user has set their own key, no ladder shown
      gift_ok       — < 50% of gift budget used
      gift_50       — 50–74% used: subtle dismissible nudge
      gift_75       — 75–89% used: persistent warning banner
      gift_90       — 90–99% used: prominent alert, actions still work
      gift_exhausted — 100%+ used: paid actions disabled
    """
    if config.has_byo_key:
        return {"state": "byo", "remaining": None, "pct": 0.0}

    total = config.total_budget
    spent = db.sum_costs_total()
    remaining = max(0.0, total - spent)
    pct = spent / total if total > 0 else 0.0

    if pct >= 1.0:
        state = "gift_exhausted"
    elif pct >= 0.9:
        state = "gift_90"
    elif pct >= 0.75:
        state = "gift_75"
    elif pct >= 0.5:
        state = "gift_50"
    else:
        state = "gift_ok"

    result: dict = {"state": state, "remaining": remaining, "pct": pct}
    if state == "gift_50":
        result["value_summary"] = db.get_value_summary()
    return result
