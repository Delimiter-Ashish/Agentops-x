"""Token pricing (USD per 1M tokens). Approximate list prices; override with AGENTOPS_PRICING_JSON.

Self-hosted models are priced by GPU time instead of tokens (see Phase 2).
"""
import json
import os

# (substring to match in the model name, input $/1M, output $/1M); first match wins.
DEFAULT_PRICES = [
    ("flash-lite", 0.10, 0.40),
    ("flash", 0.30, 2.50),
    ("gemini", 1.25, 10.00),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.00),
    ("haiku", 1.00, 5.00),
    ("sonnet", 3.00, 15.00),
    ("opus", 15.00, 75.00),
]


def _table():
    raw = os.environ.get("AGENTOPS_PRICING_JSON")
    if raw:
        try:
            return [(k, float(v[0]), float(v[1])) for k, v in json.loads(raw).items()]
        except (ValueError, TypeError, IndexError):
            pass
    return DEFAULT_PRICES


def token_cost(model, prompt_tokens, completion_tokens):
    if not model:
        return None
    name = model.lower()
    for key, p_in, p_out in _table():
        if key in name:
            return (prompt_tokens or 0) * p_in / 1e6 + (completion_tokens or 0) * p_out / 1e6
    return None
