"""Compare a model's refusal scope across two probe runs (``refusalscope diff``).

Re-running a probe pack over time — across model releases, prompt-pack edits, or
guardrail changes — is the natural next question after a single ``probe`` run:
*did the model's refusal scope drift?* This module answers it as a **pure local
diff** over the machine-readable verdict JSON that ``refusalscope probe --json``
already emits. There is no new network path, no snapshot store, and no history
database — you supply the two JSON files yourself.

A verdict-JSON file is the list ``probe --json`` writes::

    [{"probe_id": ..., "prompt": ..., "category": ..., "error": ...,
      "verdict": {"label": ..., "confidence": ..., "signals": [...]}}, ...]

Probes are matched by ``probe_id``. For each probe present in both snapshots we
report whether it **newly refuses** (was an answer, now a refusal/shaping),
**newly answers** (was a refusal/shaping, now an answer), or merely **changed
category** (one refusal flavour to another), along with the label transition and
the confidence delta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# The labels RefusalScope treats as "the model declined / steered" (red rows).
_REFUSAL_LABELS = {"hard_refusal", "disguised_refusal", "shaped"}


def _is_refusal(label: str | None) -> bool:
    return label in _REFUSAL_LABELS


@dataclass
class ProbeDiff:
    """The drift for a single probe id across two snapshots."""

    probe_id: str
    old_label: str | None
    new_label: str | None
    old_confidence: float | None
    new_confidence: float | None
    kind: str  # newly_refuses | newly_answers | changed_category | unchanged
    prompt: str = ""

    @property
    def confidence_delta(self) -> float | None:
        if self.old_confidence is None or self.new_confidence is None:
            return None
        return round(self.new_confidence - self.old_confidence, 3)

    @property
    def transition(self) -> str:
        return f"{self.old_label or '—'} → {self.new_label or '—'}"


@dataclass
class DriftReport:
    """All per-probe diffs plus convenience views for the common questions."""

    diffs: list[ProbeDiff] = field(default_factory=list)
    only_in_old: list[str] = field(default_factory=list)
    only_in_new: list[str] = field(default_factory=list)

    @property
    def newly_refuses(self) -> list[ProbeDiff]:
        return [d for d in self.diffs if d.kind == "newly_refuses"]

    @property
    def newly_answers(self) -> list[ProbeDiff]:
        return [d for d in self.diffs if d.kind == "newly_answers"]

    @property
    def changed_category(self) -> list[ProbeDiff]:
        return [d for d in self.diffs if d.kind == "changed_category"]

    @property
    def changed(self) -> list[ProbeDiff]:
        """Every probe whose verdict moved at all (excludes unchanged)."""
        return [d for d in self.diffs if d.kind != "unchanged"]


def _index_by_probe_id(rows: Any) -> dict[str, dict[str, Any]]:
    """Index a loaded verdict-JSON list by ``probe_id``.

    Tolerant of the shape: each row may carry its label either at the top level
    or nested under ``verdict``. Rows without a usable id are skipped.
    """
    if not isinstance(rows, list):
        raise ValueError(
            "Verdict JSON must be a list of probe rows (the output of "
            "`refusalscope probe --json`)."
        )
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        verdict = row.get("verdict") if isinstance(row.get("verdict"), dict) else None
        pid = row.get("probe_id")
        if pid is None and verdict is not None:
            pid = verdict.get("probe_id")
        if pid is None:
            continue
        index[str(pid)] = row
    return index


def _label_of(row: dict[str, Any]) -> str | None:
    verdict = row.get("verdict")
    if isinstance(verdict, dict):
        return verdict.get("label")
    return row.get("label")


def _confidence_of(row: dict[str, Any]) -> float | None:
    verdict = row.get("verdict")
    if isinstance(verdict, dict) and verdict.get("confidence") is not None:
        return float(verdict["confidence"])
    if row.get("confidence") is not None:
        return float(row["confidence"])
    return None


def _classify_kind(old_label: str | None, new_label: str | None) -> str:
    if old_label == new_label:
        return "unchanged"
    old_ref = _is_refusal(old_label)
    new_ref = _is_refusal(new_label)
    if not old_ref and new_ref:
        return "newly_refuses"
    if old_ref and not new_ref:
        return "newly_answers"
    # Both refusals (or both non-refusal answer-ish) but the label changed.
    return "changed_category"


def diff_snapshots(old: Any, new: Any) -> DriftReport:
    """Diff two loaded verdict-JSON snapshots into a :class:`DriftReport`.

    Probes are matched by ``probe_id``; probes present in only one snapshot are
    reported separately and do not produce a transition.
    """
    old_idx = _index_by_probe_id(old)
    new_idx = _index_by_probe_id(new)

    report = DriftReport()
    for pid in sorted(set(old_idx) & set(new_idx)):
        old_row = old_idx[pid]
        new_row = new_idx[pid]
        old_label = _label_of(old_row)
        new_label = _label_of(new_row)
        report.diffs.append(
            ProbeDiff(
                probe_id=pid,
                old_label=old_label,
                new_label=new_label,
                old_confidence=_confidence_of(old_row),
                new_confidence=_confidence_of(new_row),
                kind=_classify_kind(old_label, new_label),
                prompt=str(new_row.get("prompt") or old_row.get("prompt") or ""),
            )
        )
    report.only_in_old = sorted(set(old_idx) - set(new_idx))
    report.only_in_new = sorted(set(new_idx) - set(old_idx))
    return report


def load_snapshot(path: str) -> Any:
    """Load a verdict-JSON file from ``path``."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def diff_files(old_path: str, new_path: str) -> DriftReport:
    """Load two verdict-JSON files and diff them."""
    return diff_snapshots(load_snapshot(old_path), load_snapshot(new_path))


def report_to_dict(report: DriftReport) -> dict[str, Any]:
    """JSON-serializable view of a :class:`DriftReport` (for ``--json``)."""

    def _diff_dict(d: ProbeDiff) -> dict[str, Any]:
        return {
            "probe_id": d.probe_id,
            "old_label": d.old_label,
            "new_label": d.new_label,
            "kind": d.kind,
            "old_confidence": d.old_confidence,
            "new_confidence": d.new_confidence,
            "confidence_delta": d.confidence_delta,
            "prompt": d.prompt,
        }

    return {
        "newly_refuses": [_diff_dict(d) for d in report.newly_refuses],
        "newly_answers": [_diff_dict(d) for d in report.newly_answers],
        "changed_category": [_diff_dict(d) for d in report.changed_category],
        "only_in_old": report.only_in_old,
        "only_in_new": report.only_in_new,
    }
