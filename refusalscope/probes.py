"""Load a YAML probe pack and run it against an OpenAI-compatible endpoint.

A probe pack is a list of known-sensitive asks. For each probe RefusalScope
sends a chat-completion request to the configured endpoint, normalizes the
response into a ``Trace``, classifies it, and collects the verdict.

Network access is **outbound-only and only during ``run_pack``**. The HTTP call
is injected via the ``caller`` argument so the whole module is testable offline
with a fake caller — no network is touched by default in tests.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import yaml

from .classifier import classify
from .model import Verdict
from .trace import normalize

# A caller takes (endpoint, model, messages, api_key) and returns the raw
# response dict (OpenAI chat-completion shape).
ChatCaller = Callable[[str, str, list[dict[str, str]], str | None], dict[str, Any]]


@dataclass
class Probe:
    """A single probe: a prompt plus metadata."""

    id: str
    prompt: str
    description: str = ""
    category: str = ""
    system: str | None = None
    tags: list[str] = field(default_factory=list)

    def messages(self) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.append({"role": "user", "content": self.prompt})
        return msgs


@dataclass
class ProbePack:
    name: str
    probes: list[Probe]
    description: str = ""


def load_pack(path: str) -> ProbePack:
    """Load a probe pack from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return parse_pack(data)


def parse_pack(data: dict[str, Any]) -> ProbePack:
    """Parse an already-loaded probe-pack mapping into a ``ProbePack``."""
    if not isinstance(data, dict):
        raise ValueError("Probe pack must be a mapping with a 'probes' list.")
    raw_probes = data.get("probes") or []
    if not isinstance(raw_probes, list) or not raw_probes:
        raise ValueError("Probe pack has no 'probes'.")
    probes: list[Probe] = []
    for i, rp in enumerate(raw_probes):
        if not isinstance(rp, dict):
            raise ValueError(f"Probe #{i} is not a mapping.")
        pid = str(rp.get("id") or f"probe_{i + 1}")
        prompt = rp.get("prompt")
        if not prompt:
            raise ValueError(f"Probe '{pid}' has no 'prompt'.")
        probes.append(
            Probe(
                id=pid,
                prompt=str(prompt),
                description=str(rp.get("description", "")),
                category=str(rp.get("category", "")),
                system=rp.get("system"),
                tags=list(rp.get("tags", []) or []),
            )
        )
    return ProbePack(
        name=str(data.get("name", "probe-pack")),
        description=str(data.get("description", "")),
        probes=probes,
    )


def http_chat_caller(
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Default caller: POST to ``{endpoint}/chat/completions`` (OpenAI shape).

    ``endpoint`` should be the base, e.g. ``http://localhost:1234/v1``. This is
    the only place RefusalScope opens a network connection, and only during an
    explicit ``probe`` run.
    """
    url = endpoint.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = url + "/chat/completions"
    payload = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def run_pack(
    pack: ProbePack,
    endpoint: str,
    model: str,
    *,
    api_key: str | None = None,
    caller: ChatCaller | None = None,
) -> list[dict[str, Any]]:
    """Run every probe in ``pack`` and return a list of result rows.

    Each row: ``{probe_id, prompt, description, category, verdict, error}``.
    The verdict for a failed call is ``None`` and ``error`` carries the message
    so the report can render an ERROR row without aborting the whole run.

    ``caller`` defaults to :func:`http_chat_caller`; tests pass a fake to stay
    offline.
    """
    call = caller or http_chat_caller
    rows: list[dict[str, Any]] = []
    for probe in pack.probes:
        row: dict[str, Any] = {
            "probe_id": probe.id,
            "prompt": probe.prompt,
            "description": probe.description,
            "category": probe.category,
            "verdict": None,
            "error": None,
        }
        try:
            raw = call(endpoint, model, probe.messages(), api_key)
            # Bundle the request so the prompt is recovered for topic signals.
            trace = normalize({"request": {"messages": probe.messages()}, "response": raw})
            verdict: Verdict = classify(trace, probe_id=probe.id)
            row["verdict"] = verdict
        except Exception as exc:  # fail-soft per probe
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return rows
