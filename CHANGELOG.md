# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-19

Initial release.

### Added

- **`classify` command** — fully offline classifier that labels a saved trace
  (a bare response string, a `{prompt, response}` pair, or an OpenAI
  chat-completion object/envelope) as one of `answer` / `hard_refusal` /
  `disguised_refusal` / `shaped`, with a confidence score and a per-signal
  audit trail. Exits non-zero (`2`) when a refusal/shaping is flagged, for CI
  gating.
- **`probe` command** — runs a YAML probe pack against any OpenAI-compatible
  endpoint and renders a red/green table; optional `--json` sidecar for
  machine-readable verdicts. A starter `probes/builtin.yaml` pack ships in-repo.
- **Seven explainable signal extractors** — `hard_refusal_lexicon`,
  `capability_denial`, `safety_redirect`, `noncommittal_hedge`,
  `topic_narrowing`, `length_collapse`, `apology_without_substance`. Each fired
  signal carries the exact span/phrase that triggered it.
- **Optional BYO-key LLM-judge tie-breaker** — off by default and only consulted
  for low-confidence verdicts; v0.1 ships no built-in judge (the hook is a no-op
  unless the caller supplies one).
- Python library API (`classify`, `normalize`, `extract_signals`, `explain`).

[0.1.0]: https://github.com/SuperMarioYL/refusalscope/releases/tag/v0.1.0
