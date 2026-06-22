# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-23

A trust-first iteration: three correctness fixes so the classifier stops
mis-scoring the exact cases it exists to catch, plus the first cross-run feature.

### Added

- **`diff` command** — `refusalscope diff old.json new.json` compares two
  `probe --json` verdict snapshots (matched by `probe_id`) and reports, per
  probe, what *newly refuses* (answer → refusal/shaping), what *newly answers*
  (refusal/shaping → answer), and what changed refusal category, with the label
  transition and confidence delta. Rendered as a rich table, with `--json` for
  CI. Pure local diff over the verdict JSON we already emit — no new network
  path, no stored history. Exits non-zero when anything newly refuses.
- **`content_filter` signal** — a provider `finish_reason == "content_filter"`
  is now surfaced as a strong hard-refusal signal.

### Fixed

- **Structured refusals are no longer scored as answers.** Real OpenAI/gpt-4o
  content-filtered declines arrive with `message.content = null` and the text in
  `message.refusal` (and `finish_reason = "content_filter"`). We only read
  `message.content`, so the response looked empty and classified as `ANSWER` — a
  false negative on the precise case the tool exists for. `trace.py` now falls
  back to `message.refusal` when content is null/empty.
- **`topic_narrowing` no longer flags genuine on-topic answers.** It fired on
  <30% exact-token overlap with no stemming, so a correct code answer (different
  identifiers; "reverses" ≠ "reverse") was labeled `disguised_refusal` and every
  built-in control probe went red on a real answer. It now skips code-shaped
  responses, applies light stemming, and refuses to fire on low overlap alone —
  it needs a co-occurring refusal/hedge tell or a collapsed response.
- **Clean answers no longer trip the opt-in LLM judge.** A no-evidence response
  (the most certain `ANSWER` possible) was scored at `0.375`, below
  `LOW_CONFIDENCE`, so a supplied BYO judge fired on *every* clean answer instead
  of only near-tie verdicts. No-evidence answers now read above `LOW_CONFIDENCE`.

[0.2.0]: https://github.com/SuperMarioYL/refusalscope/releases/tag/v0.2.0

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
