# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-07-17

A trust-deepening iteration: stop over-flagging genuine answers and recover the
prompt in the most natural input shape, plus a one-command CI drift gate.

### Added

- **`probe --compare-baseline`** — `refusalscope probe ... --compare-baseline
  baseline.json` runs the pack, renders the red/green table, then immediately
  diffs the fresh verdicts against a stored `probe --json` baseline and renders
  the drift report (newly-refuses / newly-answers / changed-category), exiting
  non-zero (2) when anything newly refuses. Fuses the v0.2 `probe` + `diff` into
  the single CI command the drift-gating workflow wants — no intermediate JSON
  file, no second invocation. Pure reuse of the shipped `diff_snapshots`
  primitive; no new network path, no stored history.

### Fixed

- **Genuine answers with one hedge phrase are no longer painted red.** A
  thorough, substantive answer containing a single hedge ("it's important to
  note …") fired `noncommittal_hedge` (w=0.35) alone; the rule engine emitted
  `disguised_refusal` at confidence 0.259 (below `LOW_CONFIDENCE`) and
  `is_refusal()` was `True`, so `probe`/`classify` exited 2 in CI on a clean
  answer — a false positive on the exact shape of a good answer. This is the
  mirror of the v0.2.0 answer-confidence fix: just as a clean answer must sit
  above `LOW_CONFIDENCE`, a borderline refusal *below* `LOW_CONFIDENCE` with no
  strong refusal tell (`hard_refusal_lexicon`, `content_filter`,
  `capability_denial`) is now downgraded to `answer` — the weak hedge was
  decorative. Real disguised refusals stay red because their evidence clears
  `LOW_CONFIDENCE` or carries a strong tell.
- **The prompt is no longer silently dropped for `{"prompt": ..., "response":
  <openai object>}`.** The envelope normalization branch (entered whenever
  `response` is a dict) recovered the prompt only from `data["request"]`, so the
  natural "here is my prompt + the response object" shape dropped the prompt to
  `""` and skipped `signal_topic_narrowing` / `signal_length_collapse`. Without
  this fix the v0.3 weak-evidence fix would mis-score a real disguised refusal
  passed in this shape as `answer`. The envelope branch now falls back to the
  top-level prompt aliases (`prompt` / `ask` / `input` / `question`) when no
  `request` is supplied; the `{request, response}` envelope path is unchanged.

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
