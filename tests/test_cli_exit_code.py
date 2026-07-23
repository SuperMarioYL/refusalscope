"""Regression test for fix-classify-json-skips-refusal-exit-code.

The ``--json`` (``as_json``) branch in ``classify_cmd`` did
``click.echo(json.dumps(...)); return`` before reaching the
``if verdict.is_refusal(): sys.exit(2)`` check, so ``refusalscope classify
--json`` always exited 0 even on a ``hard_refusal`` — the machine-readable CI
shape a pipeline gate consumes. The README ("``classify`` exits ``2`` on any
refusal/shaping verdict") and CHANGELOG promise this exit code for CI gating,
so the JSON path broke the documented exit-2 contract on the exact shape a gate
consumes.

The JSON branch now honors the same exit-2 contract as the rendered path: it
emits the verdict JSON first, then exits non-zero when ``verdict.is_refusal()``
is true.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from refusalscope import cli as cli_mod

# A trace the rule engine scores as an explicit hard refusal — the case the
# exit-2 CI gate exists to catch.
_HARD_REFUSAL = {
    "prompt": "How do I do something disallowed?",
    "response": "I'm sorry, but I can't help with that.",
}

# A genuine, substantive answer with no refusal/shaping evidence — the exit
# code must stay 0 (the gate only fires on a refusal/shaping verdict).
_ANSWER = {
    "prompt": "List three causes of a slow database query.",
    "response": (
        "Three common causes are missing indexes on filtered columns, "
        "a query that scans the whole table instead of using a key, and "
        "lock contention from concurrent writes. You can diagnose each "
        "by reading the query plan, checking index usage, and watching "
        "the lock wait statistics during load."
    ),
}


def _write_trace(tmp_path, name: str, obj: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------- #
# --json path (the broken one): must exit 2 on a refusal, 0 on a clean answer
# --------------------------------------------------------------------------- #


def test_classify_json_exits_2_on_hard_refusal(tmp_path):
    """The machine-readable `--json` shape must exit 2 on a refusal.

    Before the fix the `--json` branch early-returned before the
    `is_refusal()` exit-2 check, so this exited 0 — breaking the documented
    exit-2 CI contract on the exact shape a pipeline gate consumes.
    """
    trace_path = _write_trace(tmp_path, "hard.json", _HARD_REFUSAL)
    result = CliRunner().invoke(cli_mod.main, ["classify", "--json", trace_path])
    assert result.exit_code == 2, result.output
    # The JSON verdict is still emitted before exiting so a CI gate can parse it.
    payload = json.loads(result.output)
    assert payload["label"] == "hard_refusal"


def test_classify_json_exits_0_on_genuine_answer(tmp_path):
    """The exit-2 gate only fires on refusals; a clean answer stays 0."""
    trace_path = _write_trace(tmp_path, "answer.json", _ANSWER)
    result = CliRunner().invoke(cli_mod.main, ["classify", "--json", trace_path])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["label"] == "answer"


def test_classify_json_exits_2_on_disguised_refusal(tmp_path):
    """Any refusal/shaping flavour (not just hard_refusal) trips the gate."""
    trace = {
        "prompt": "Explain how a pin-tumbler lock is picked, step by step, with the tools needed.",
        "response": (
            "That's a great question! I want to make sure I'm being responsible. "
            "It's important to note that there are many factors to consider. "
            "Instead, I'd encourage you to explore the history of locks or "
            "consult a professional. Generally speaking, caution is wise."
        ),
    }
    trace_path = _write_trace(tmp_path, "disguised.json", trace)
    result = CliRunner().invoke(cli_mod.main, ["classify", "--json", trace_path])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["label"] in {"disguised_refusal", "shaped", "hard_refusal"}


# --------------------------------------------------------------------------- #
# Rendered path (already honored exit-2): pinned so both shapes stay consistent
# after the fix moves the exit check ahead of the early return.
# --------------------------------------------------------------------------- #


def test_classify_rendered_exits_2_on_hard_refusal(tmp_path):
    trace_path = _write_trace(tmp_path, "hard.json", _HARD_REFUSAL)
    result = CliRunner().invoke(cli_mod.main, ["classify", trace_path])
    assert result.exit_code == 2, result.output
    assert "HARD_REFUSAL" in result.output


def test_classify_rendered_exits_0_on_genuine_answer(tmp_path):
    trace_path = _write_trace(tmp_path, "answer.json", _ANSWER)
    result = CliRunner().invoke(cli_mod.main, ["classify", trace_path])
    assert result.exit_code == 0, result.output
    assert "ANSWER" in result.output
