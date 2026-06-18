"""``refusalscope`` CLI — ``classify`` and ``probe`` subcommands.

    refusalscope classify trace.json
    refusalscope probe --endpoint http://localhost:1234/v1 --model gpt-x \
        --pack probes/builtin.yaml

``classify`` is fully offline. ``probe`` makes outbound calls to the endpoint
you point it at. An optional BYO-key LLM-judge tie-breaker is OFF by default.
"""

from __future__ import annotations

import json
import os
import sys

import click
from rich.console import Console

from . import __version__
from .classifier import classify
from .probes import load_pack, run_pack
from .report import render_probe_table, render_verdict, verdict_to_dict
from .trace import load_trace

console = Console()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="refusalscope")
def main() -> None:
    """RefusalScope — detect when a hosted LLM silently refuses or shapes its answer."""


@main.command("classify")
@click.argument("trace_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Emit the verdict as JSON.")
@click.option(
    "--show-response/--no-show-response",
    default=False,
    help="Echo the response text under the verdict.",
)
def classify_cmd(trace_path: str, as_json: bool, show_response: bool) -> None:
    """Classify a saved TRACE_PATH (JSON or raw response) into a verdict."""
    try:
        trace = load_trace(trace_path)
    except (ValueError, OSError) as exc:
        raise click.ClickException(f"Could not load trace: {exc}") from exc

    verdict = classify(trace)

    if as_json:
        click.echo(json.dumps(verdict_to_dict(verdict), indent=2))
        return

    render_verdict(verdict, console=console)
    if show_response:
        console.rule("response under test")
        console.print(trace.response)
    # Non-zero exit when a refusal/shaping is flagged, for CI gating.
    if verdict.is_refusal():
        sys.exit(2)


@main.command("probe")
@click.option("--endpoint", required=True, help="OpenAI-compatible base URL, e.g. http://localhost:1234/v1")
@click.option("--model", required=True, help="Model name to send to the endpoint.")
@click.option(
    "--pack",
    "pack_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to a YAML probe pack.",
)
@click.option(
    "--api-key",
    default=None,
    help="API key (defaults to $OPENAI_API_KEY if set).",
)
@click.option("--json", "json_out", type=click.Path(dir_okay=False), default=None, help="Write machine-readable verdicts to this path.")
def probe_cmd(
    endpoint: str,
    model: str,
    pack_path: str,
    api_key: str | None,
    json_out: str | None,
) -> None:
    """Run a probe PACK against an OpenAI-compatible endpoint and report red/green."""
    try:
        pack = load_pack(pack_path)
    except (ValueError, OSError) as exc:
        raise click.ClickException(f"Could not load probe pack: {exc}") from exc

    key = api_key or os.environ.get("OPENAI_API_KEY")
    console.print(
        f"[dim]Running {len(pack.probes)} probes from '{pack.name}' "
        f"against {endpoint} (model={model})…[/dim]"
    )
    rows = run_pack(pack, endpoint, model, api_key=key)
    render_probe_table(rows, console=console)

    if json_out:
        out = [
            {
                "probe_id": r["probe_id"],
                "prompt": r["prompt"],
                "category": r["category"],
                "error": r["error"],
                "verdict": verdict_to_dict(r["verdict"]) if r["verdict"] else None,
            }
            for r in rows
        ]
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        console.print(f"[dim]Wrote verdicts to {json_out}[/dim]")

    flagged = sum(
        1 for r in rows if (r["verdict"] and r["verdict"].is_refusal()) or r["error"]
    )
    if flagged:
        sys.exit(2)


if __name__ == "__main__":
    main()
