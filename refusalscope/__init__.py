"""RefusalScope — detect when a hosted LLM silently refuses or shapes its answer.

RefusalScope turns a hosted-LLM response into a trustworthy verdict:
``classify(Trace) -> Verdict`` where the label is one of
``answer | hard_refusal | disguised_refusal | shaped`` and every label
carries the per-signal evidence that produced it.

Offline-first: classification is rules + signal heuristics with no network
calls. An optional BYO-key LLM-judge tie-breaker is opt-in and OFF by default.
"""

from __future__ import annotations

__version__ = "0.8.0"

from .classifier import classify
from .model import Signal, Trace, Verdict, VerdictLabel
from .trace import normalize

__all__ = [
    "Signal",
    "Trace",
    "Verdict",
    "VerdictLabel",
    "__version__",
    "classify",
    "normalize",
]
