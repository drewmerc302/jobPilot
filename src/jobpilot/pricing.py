"""Anthropic pricing table + estimator.

Rates are USD per 1M tokens (input, output). Aliases without date
suffix (e.g. ``claude-sonnet-4-6``) resolve to the dated entry.
"""

import logging
import re

logger = logging.getLogger(__name__)

_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-6-20250929": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
    "claude-opus-4-7-20251215": (15.00, 75.00),
    "claude-opus-4-5": (15.00, 75.00),
}

# Default fallback (sonnet-class) used when we don't know a model.
_DEFAULT_RATES: tuple[float, float] = (3.00, 15.00)

# Strip a trailing "-YYYYMMDD" date suffix, e.g.
# "claude-sonnet-4-6-20250929" -> "claude-sonnet-4-6".
_DATE_SUFFIX = re.compile(r"-\d{8}$")


def _normalize(model: str) -> str:
    if not model:
        return model
    if model in _PRICING:
        return model
    stripped = _DATE_SUFFIX.sub("", model)
    if stripped in _PRICING:
        return stripped
    return model


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = _normalize(model)
    rates = _PRICING.get(key)
    if rates is None:
        logger.warning(
            "Unknown model %r in pricing table; defaulting to sonnet-class rates",
            model,
        )
        rates = _DEFAULT_RATES
    in_rate, out_rate = rates
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
