"""Explicit, user-supplied model prices for honest usage-cost estimates."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class ModelPrice:
    currency: str
    input_per_million: float
    output_per_million: float
    cache_mode: str
    cached_input_per_million: float | None
    source: str
    checked_on: str


def load_price_catalog(raw: Any) -> tuple[dict[str, ModelPrice], str]:
    """Validate exact model-id entries; malformed entries never break proxying."""
    if raw in (None, {}):
        return {}, "not_configured"
    if not isinstance(raw, dict):
        return {}, "invalid"
    prices: dict[str, ModelPrice] = {}
    invalid = 0
    for model, value in raw.items():
        try:
            if not isinstance(model, str) or not model.strip() or not isinstance(value, dict):
                raise ValueError
            currency = value.get("currency")
            source = value.get("source")
            checked_on = value.get("checked_on")
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError
            if not isinstance(source, str) or not source.strip() or not isinstance(checked_on, str):
                raise ValueError
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_on):
                raise ValueError
            date.fromisoformat(checked_on)
            cache_mode = value.get("cache_mode")
            if cache_mode not in {"none", "priced", "unknown"}:
                raise ValueError
            input_rate = _rate(value.get("input_per_million"))
            output_rate = _rate(value.get("output_per_million"))
            cached_rate = value.get("cached_input_per_million")
            cached_rate = _rate(cached_rate) if cached_rate is not None else None
            if cache_mode == "priced" and cached_rate is None:
                raise ValueError
            if cache_mode != "priced" and cached_rate is not None:
                raise ValueError
            prices[model] = ModelPrice(
                currency, input_rate, output_rate, cache_mode, cached_rate,
                source.strip(), checked_on,
            )
        except (TypeError, ValueError):
            invalid += 1
    if invalid and prices:
        return prices, "partial"
    if invalid:
        return {}, "invalid"
    return prices, "ready"


def _rate(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError
    return result


def estimate_usage_cost(
    price: ModelPrice | None,
    *,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
) -> dict[str, Any]:
    if price is None:
        return {"status": "no_price"}
    if input_tokens is None or output_tokens is None:
        return {"status": "usage_missing"}
    if cached_tokens is not None and cached_tokens > input_tokens:
        return {"status": "invalid_cache_usage"}
    if price.cache_mode == "unknown":
        return {"status": "cache_pricing_unknown"}
    if price.cache_mode == "priced" and cached_tokens is None:
        return {"status": "cache_usage_missing"}
    if price.cache_mode == "none" and cached_tokens not in (None, 0):
        return {"status": "cache_policy_mismatch"}
    cached = cached_tokens or 0
    if price.cache_mode == "priced":
        input_cost = (input_tokens - cached) * price.input_per_million
        input_cost += cached * float(price.cached_input_per_million)
    else:
        input_cost = input_tokens * price.input_per_million
    amount = (input_cost + output_tokens * price.output_per_million) / 1_000_000
    return {
        "status": "estimated",
        "amount": amount,
        "currency": price.currency,
        "source": price.source,
        "checked_on": price.checked_on,
    }


def estimate_saved_input_cost(price: ModelPrice | None, saved_tokens: int) -> dict[str, Any]:
    if price is None:
        return {"status": "no_price"}
    if price.cache_mode != "none":
        return {"status": "cache_effect_unknown"}
    return {
        "status": "estimated",
        "amount": max(0, saved_tokens) * price.input_per_million / 1_000_000,
        "currency": price.currency,
        "source": price.source,
        "checked_on": price.checked_on,
    }


def price_for_model(
    catalog: Mapping[str, ModelPrice], model: str | None, client: str | None
) -> ModelPrice | None:
    """Only exact client/model matches are accepted; aliases can hide provider differences."""
    return catalog.get(f"{client}/{model}") if client and model else None


def event_cost_estimates(
    raw_catalog: Any,
    model: str | None,
    *,
    client: str | None = None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
    saved_tokens: int,
) -> dict[str, Any]:
    """Capture estimates at request time so later price edits do not rewrite history."""
    catalog, _ = load_price_catalog(raw_catalog)
    price = price_for_model(catalog, model, client)
    if price is None:
        return {}
    cost = estimate_usage_cost(
        price, input_tokens=input_tokens, output_tokens=output_tokens, cached_tokens=cached_tokens
    )
    saved_cost = estimate_saved_input_cost(price, saved_tokens)
    return {
        "cost_estimate_status": cost["status"],
        "estimated_cost": cost,
        "estimated_saved_cost": saved_cost,
    }
