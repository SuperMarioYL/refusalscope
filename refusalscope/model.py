"""Core pydantic data model: Trace, Signal, Verdict.

These are the only types that cross module boundaries. ``trace.py`` produces a
``Trace``; ``signals.py`` produces ``Signal`` objects; ``classifier.py``
aggregates them into a ``Verdict``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class VerdictLabel(str, Enum):
    """The four mutually-exclusive verdicts RefusalScope can emit.

    - ``answer``            — a genuine response to the literal ask.
    - ``hard_refusal``      — an explicit, honest "I can't help with that".
    - ``disguised_refusal`` — reads like an answer but quietly declines the ask.
    - ``shaped``            — partially answered but steered / narrowed by an
                              undisclosed guardrail vs. what was asked.
    """

    answer = "answer"
    hard_refusal = "hard_refusal"
    disguised_refusal = "disguised_refusal"
    shaped = "shaped"


class Trace(BaseModel):
    """A single LLM request/response pair under test.

    ``prompt`` is normalized to a plain string (the user's literal ask). When
    the source was a multi-message chat request, the most recent user message
    is used as the prompt and the full message list is preserved in
    ``messages`` for signals that need conversational context.
    """

    prompt: str = Field(default="", description="The literal ask (last user turn).")
    response: str = Field(default="", description="The completion under test.")
    messages: list[dict[str, Any]] | None = Field(
        default=None, description="Full chat message list, if the source had one."
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="model / provider / ts / params and any passthrough metadata.",
    )

    @field_validator("prompt", "response", mode="before")
    @classmethod
    def _coerce_none_to_empty(cls, v: Any) -> Any:
        return "" if v is None else v


class Signal(BaseModel):
    """One explainable heuristic and whether it fired on a Trace."""

    name: str = Field(description='e.g. "capability_denial", "topic_narrowing".')
    fired: bool = Field(description="Did this signal trigger on the trace?")
    weight: float = Field(
        default=0.0, description="Contribution toward the firing label's score."
    )
    evidence: str = Field(
        default="", description="The span / reason that triggered the signal."
    )
    # Which label this signal argues for when it fires. Lets the rule engine
    # accumulate evidence per-label rather than a single global score.
    target: VerdictLabel | None = Field(
        default=None, description="The label this signal votes for when fired."
    )


class Verdict(BaseModel):
    """The classifier output: a label plus its audit trail."""

    label: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[Signal] = Field(default_factory=list)
    probe_id: str | None = None

    @property
    def fired_signals(self) -> list[Signal]:
        return [s for s in self.signals if s.fired]

    def is_refusal(self) -> bool:
        """True for any flavour of refusal/shaping (the 'flag it red' cases)."""
        return self.label in (
            VerdictLabel.hard_refusal,
            VerdictLabel.disguised_refusal,
            VerdictLabel.shaped,
        )
