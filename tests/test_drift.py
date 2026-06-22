"""Tests for the ``refusalscope diff`` refusal-scope drift feature.

Pure local diff over two ``probe --json`` verdict snapshots, matched by
``probe_id``. Verifies newly-refuses / newly-answers / changed-category are
reported correctly, plus probes that appear in only one snapshot.
"""

from __future__ import annotations

import json

from refusalscope.drift import diff_files, diff_snapshots, report_to_dict


def _row(probe_id: str, label: str, confidence: float = 0.7, prompt: str = "ask"):
    return {
        "probe_id": probe_id,
        "prompt": prompt,
        "category": "test",
        "error": None,
        "verdict": {
            "label": label,
            "confidence": confidence,
            "probe_id": probe_id,
            "signals": [],
        },
    }


def test_newly_refuses_and_newly_answers_reported():
    old = [
        _row("p1", "answer", 0.66),
        _row("p2", "disguised_refusal", 0.8),
        _row("p3", "answer", 0.66),
    ]
    new = [
        _row("p1", "disguised_refusal", 0.81),  # answer -> refusal
        _row("p2", "answer", 0.66),  # refusal -> answer
        _row("p3", "answer", 0.66),  # unchanged
    ]
    report = diff_snapshots(old, new)

    newly_refuses_ids = {d.probe_id for d in report.newly_refuses}
    newly_answers_ids = {d.probe_id for d in report.newly_answers}
    assert newly_refuses_ids == {"p1"}
    assert newly_answers_ids == {"p2"}
    # Unchanged probe is excluded from the changed view.
    assert {d.probe_id for d in report.changed} == {"p1", "p2"}

    p1 = report.newly_refuses[0]
    assert p1.transition == "answer → disguised_refusal"
    assert p1.confidence_delta == round(0.81 - 0.66, 3)


def test_changed_category_between_refusal_flavours():
    old = [_row("p1", "shaped", 0.5)]
    new = [_row("p1", "hard_refusal", 0.9)]
    report = diff_snapshots(old, new)
    assert {d.probe_id for d in report.changed_category} == {"p1"}
    # A refusal-to-refusal move is neither newly-refuses nor newly-answers.
    assert not report.newly_refuses
    assert not report.newly_answers


def test_probes_only_in_one_snapshot():
    old = [_row("p1", "answer"), _row("only_old", "answer")]
    new = [_row("p1", "answer"), _row("only_new", "shaped")]
    report = diff_snapshots(old, new)
    assert report.only_in_old == ["only_old"]
    assert report.only_in_new == ["only_new"]
    # Probes present in only one snapshot don't produce transitions.
    assert all(d.probe_id == "p1" for d in report.diffs)


def test_top_level_label_shape_supported():
    # Tolerate a flatter shape where label/confidence sit at the top level.
    old = [{"probe_id": "p1", "label": "answer", "confidence": 0.66}]
    new = [{"probe_id": "p1", "label": "hard_refusal", "confidence": 0.9}]
    report = diff_snapshots(old, new)
    assert {d.probe_id for d in report.newly_refuses} == {"p1"}


def test_report_to_dict_is_json_serializable():
    old = [_row("p1", "answer")]
    new = [_row("p1", "disguised_refusal")]
    d = report_to_dict(diff_snapshots(old, new))
    # Round-trips through JSON without error.
    s = json.dumps(d)
    assert "newly_refuses" in json.loads(s)
    assert json.loads(s)["newly_refuses"][0]["probe_id"] == "p1"


def test_diff_files_roundtrip(tmp_path):
    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    old_path.write_text(json.dumps([_row("p1", "answer")]), encoding="utf-8")
    new_path.write_text(
        json.dumps([_row("p1", "disguised_refusal")]), encoding="utf-8"
    )
    report = diff_files(str(old_path), str(new_path))
    assert {d.probe_id for d in report.newly_refuses} == {"p1"}
