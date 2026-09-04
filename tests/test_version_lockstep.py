"""Single-source-of-truth version lockstep test.

Asserts every user-facing version surface agrees on one version string:

  VERSION file == __version__ == web/site.json content_version
                 == CHANGELOG head == CLI --version

This test FAILS on the v0.6.0 tag because ``web/site.json`` still carried
``content_version: "v0.5.0"`` (the v0.5.0 release bumped it, but the v0.6.0
release did not), while every other surface read ``0.6.0``. That drift is the
bug this test pins.
"""

from __future__ import annotations

import json
import os
import re

from click.testing import CliRunner

from refusalscope import __version__
from refusalscope import cli as cli_mod

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_version_file() -> str:
    with open(os.path.join(_REPO_ROOT, "VERSION"), encoding="utf-8") as fh:
        return fh.read().strip()


def _read_site_content_version() -> str:
    with open(os.path.join(_REPO_ROOT, "web", "site.json"), encoding="utf-8") as fh:
        return json.load(fh)["content_version"].lstrip("v")


def _read_changelog_head() -> str:
    with open(os.path.join(_REPO_ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^##\s*\[([0-9][^\]]*)\]", line)
            if m:
                return m.group(1).strip()
    raise AssertionError("no version heading found in CHANGELOG.md")


def _read_cli_version() -> str:
    result = CliRunner().invoke(cli_mod.main, ["--version"])
    assert result.exit_code == 0, result.output
    # click prints "<prog_name>, version <version>" — pull the last token.
    return result.output.strip().split()[-1]


def test_all_version_surfaces_agree():
    surfaces = {
        "VERSION": _read_version_file(),
        "__version__": __version__,
        "site.content_version": _read_site_content_version(),
        "CHANGELOG head": _read_changelog_head(),
        "CLI --version": _read_cli_version(),
    }
    versions = set(surfaces.values())
    assert len(versions) == 1, (
        f"version surfaces disagree: {surfaces}"
    )
