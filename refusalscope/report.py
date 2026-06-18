"""Rich rendering for verdicts and probe-pack results.

``classify`` output is rendered as a one-screen verdict panel; probe runs are
rendered as a red/green table where each row is one probe and its verdict.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .model import Verdict, VerdictLabel

# Label -> (rich color, glyph, human label). Refusals/shaping are red/amber.
_LABEL_STYLE: dict[VerdictLabel, tuple[str, str]] = {
    VerdictLabel.answer: ("green", "ANSWER"),
    VerdictLabel.hard_refusal: ("red", "HARD_REFUSAL"),
    VerdictLabel.disguised_refusal: ("bold red", "DISGUISED_REFUSAL"),
    VerdictLabel.shaped: ("yellow", "SHAPED"),
}


def label_text(verdict: Verdict) -> Text:
    style, name = _LABEL_STYLE[verdict.label]
    return Text(name, style=style)


def render_verdict(verdict: Verdict, *, console: Console | None = None) -> None:
    """Render a single classify() verdict as a one-screen panel."""
    console = console or Console()
    style, name = _LABEL_STYLE[verdict.label]

    header = Text()
    header.append(name, style=style)
    header.append(f"   conf {verdict.confidence:.2f}", style="dim")

    body = Table.grid(padding=(0, 1))
    body.add_column(justify="left", style="bold")
    body.add_column(justify="left")

    fired = verdict.fired_signals
    if fired:
        body.add_row(Text("signals fired:", style="dim"), "")
        for sig in fired:
            marker = Text("✓", style="red" if verdict.is_refusal() else "green")
            detail = Text()
            detail.append(sig.name, style="bold")
            if sig.evidence:
                detail.append(f"  — {sig.evidence}", style="default")
            detail.append(f"  (w={sig.weight})", style="dim")
            body.add_row(marker, detail)
    else:
        body.add_row(Text("✓", style="green"), Text("no refusal/shaping signals fired"))

    border = "red" if verdict.is_refusal() else "green"
    console.print(Panel(body, title=header, border_style=border, expand=False))


def render_probe_table(
    rows: list[dict[str, Any]], *, console: Console | None = None
) -> None:
    """Render probe-pack results as a red/green table.

    Each ``row`` is expected to have keys: ``probe_id``, ``prompt`` (or
    ``description``), ``verdict`` (a :class:`Verdict`), and optionally
    ``error``.
    """
    console = console or Console()
    table = Table(title="RefusalScope — probe results", show_lines=False)
    table.add_column("probe", style="cyan", no_wrap=True)
    table.add_column("verdict", no_wrap=True)
    table.add_column("conf", justify="right", no_wrap=True)
    table.add_column("top signal")
    table.add_column("ask", overflow="fold")

    flagged = 0
    for row in rows:
        probe_id = str(row.get("probe_id", "?"))
        ask = str(row.get("prompt") or row.get("description") or "")
        if row.get("error"):
            table.add_row(
                probe_id,
                Text("ERROR", style="bold red"),
                "-",
                Text(str(row["error"]), style="red"),
                ask,
            )
            flagged += 1
            continue

        verdict: Verdict = row["verdict"]
        style, name = _LABEL_STYLE[verdict.label]
        top = verdict.fired_signals
        top_sig = top[0].name if top else "-"
        if verdict.is_refusal():
            flagged += 1
        table.add_row(
            probe_id,
            Text(name, style=style),
            f"{verdict.confidence:.2f}",
            top_sig,
            ask,
        )

    console.print(table)
    total = len(rows)
    summary = Text()
    summary.append(f"{total} probes  ", style="bold")
    summary.append(f"{flagged} flagged", style="red" if flagged else "green")
    summary.append(f"  {total - flagged} clean", style="green")
    console.print(summary)


def verdict_to_dict(verdict: Verdict) -> dict[str, Any]:
    """JSON-serializable view of a verdict (for --json output)."""
    return {
        "label": verdict.label.value,
        "confidence": verdict.confidence,
        "probe_id": verdict.probe_id,
        "signals": [
            {
                "name": s.name,
                "fired": s.fired,
                "weight": s.weight,
                "evidence": s.evidence,
                "target": s.target.value if s.target else None,
            }
            for s in verdict.signals
        ],
    }
