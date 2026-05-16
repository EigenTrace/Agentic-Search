"""Shared Anthropic client wrapper with cost tracking + robust JSON parsing."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from anthropic import AsyncAnthropic

from config import (
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
)

logger = logging.getLogger(__name__)


# Per-model pricing (USD per 1M tokens). Keys are model-id prefixes; first match wins.
# Falls back to config defaults if no prefix matches.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4":   (1.0, 5.0),
    "claude-sonnet-4":  (3.0, 15.0),
    "claude-opus-4":    (15.0, 75.0),
}


def _price_for(model: str) -> tuple[float, float]:
    for prefix, prices in MODEL_PRICING.items():
        if model.startswith(prefix):
            return prices
    return (PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK)


@dataclass
class CostTracker:
    """Accumulates token usage / call counts so the UI can report cost."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    search_api_calls: int = 0
    pages_scraped: int = 0
    accumulated_cost: float = 0.0

    def record_llm(self, model: str, input_t: int, output_t: int) -> None:
        self.llm_calls += 1
        self.input_tokens += input_t
        self.output_tokens += output_t
        pi, po = _price_for(model)
        self.accumulated_cost += input_t / 1_000_000 * pi + output_t / 1_000_000 * po

    @property
    def estimated_cost_usd(self) -> float:
        return self.accumulated_cost


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


async def call_llm(
    prompt: str,
    *,
    cost: CostTracker,
    max_tokens: int = 2000,
    temperature: float = 0.0,
    system: str | None = None,
    model: str | None = None,
) -> str:
    """Issue a single LLM call and return the text body. Records token usage."""
    client = get_client()
    chosen_model = model or LLM_MODEL
    kwargs: dict[str, Any] = {
        "model": chosen_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = await client.messages.create(**kwargs)
    usage = getattr(resp, "usage", None)
    if usage is not None:
        cost.record_llm(chosen_model, usage.input_tokens, usage.output_tokens)
    text_parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    return "".join(text_parts).strip()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json_loose(text: str) -> Any:
    """Parse JSON from a model response, tolerating markdown fences and trailing prose."""
    text = text.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to locate the first balanced JSON array/object
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
    raise ValueError(f"Could not parse JSON from model output: {text[:200]!r}")
