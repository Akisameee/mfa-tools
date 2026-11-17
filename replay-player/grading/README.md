# Recorded annotation grading

[English](README.md) | [简体中文](README.zh-CN.md)

An offline script using a Chat Completions-compatible API. It adds files under
the recording's `grading/` directory without modifying `events.jsonl`,
`manifest.json`, or `states/`. Requires Python 3.11 or later.

## Configuration

For first-time setup, copy `config.example.toml` in this directory to
`config.toml`, then edit **`config.toml`**:

```toml
base_url = "https://your-provider/v1"
model = "your-model"
api_key_env = "GRADING_API_KEY"
api_key = ""
batch_size = 12
concurrency = 2
timeout_seconds = 120
retry_attempts = 3
json_mode = true

[request]
```

Set the key in the PowerShell window used to run the script:

```powershell
$env:GRADING_API_KEY = "your API key"
```

Alternatively, set `api_key` in the local `config.toml`. The environment variable
takes priority. The local configuration is ignored by Git; never put real keys
in `config.example.toml`. `GRADING_BASE_URL` and `GRADING_MODEL` also override
the corresponding file settings.

Use your provider's compatible base URL; the script appends `/chat/completions`.
If the URL already ends in `/chat/completions`, it is used directly.
Keys are not written to scores, metadata, or request statistics.

API requests use the standard-library HTTP client, with no SDK required.
JSON output parameters follow the
[Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [JSON mode](https://api-docs.deepseek.com/guides/json_mode/).
For providers that do not support this parameter, set `json_mode = false`;
responses must still be valid JSON and are strictly validated.
Provider-specific parameters can go under `[request]`, such as supported
`max_tokens` or `max_completion_tokens`; do not set both. Parameters such as
temperature are not added by default.

## Run

Run all commands below from the workspace root. `uv` supplies UnityPy and
PyCryptodome for extracting reference data.

Extract reference data only, **without calling the API**:

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py --prepare-only
```

Grade 20 uncached combinations first to check the grading standard:

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py --limit 20
```

Grade all remaining combinations:

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/grading/evaluate.py
```

By default, the script processes the recording currently referenced by
`replay-player/data/replay.json`. Use `--recording recordings` for a newer recording
written directly to the root directory, or `--recording recordings/old-recording-ID`
for an older recording. Without prepared playback data, a nonempty root log is
preferred, with legacy recording directories as fallback. `--assets` changes the
game asset path; `--config` selects another configuration file.

Reruns resume the work: successfully graded identical combinations are not
requested again. Changes to the model, base URL, request parameters, prompt, or
reference data create a new cache context. API failures do not become red grades;
they are logged in `errors.jsonl` and retried on the next run. Items the model
cannot determine are saved as `unresolved`; use `--retry-unresolved` to retry them,
or inspect their reasons manually first.

## Results

```text
recordings/grading/
  reference.json   # Internal English names, full dictionary definitions, parts of speech,
                   # components, and original number/unit notation
  items.json       # Deduplicated combinations and reference data for spot checks
  scores.jsonl     # Grades and short reasons, retaining results from past models/rules
  metadata.json    # Current model, rule/asset fingerprints, counts; no keys
  requests.jsonl   # Item IDs for each request and token usage returned by the API
  errors.jsonl     # Failed requests; created only when errors occur
```

`--prepare-only` generates only the first two files and leaves the current grading
context unchanged. Reference answers come from the game's `newalien` vocabulary:
the English `word` name and original `meaning` are preserved, with parts of speech
and component information added according to the game's entry structure.
Dictionary entries are the author's symbolic English sentences, without automatic
translation into Chinese. Component descriptions explain character construction,
not the meaning itself. A numeric key such as `4e1` has the exact value `4×7=28`;
the reference explicitly records the number base and preserves original number
and unit notation.

Only `arguments.text` from successful `note` calls is graded. Characters are
identified by `character.key` in that call's result. Annotations are not extracted
from snapshots, `look`, or game display text. Failed writes, cleared annotations,
and inputs containing only `?` are not submitted. There is no need to parse or
strip the game's automatic annotations: parentheses, numbers, and units in the
input are the player's original text and are preserved in full.

Edit grading rules in `prompt.md`: green means correct, yellow means close or
incomplete, and red means wrong. A question mark alone does not lower the grade;
an accurate common meaning need not list every use. Items without reliable
evidence remain ungraded.

## Player integration

When a run finishes or is interrupted, saved results are automatically attached
to `replay-player/data/grading.json` **if it matches that recording**. This playback
copy contains grades, reasons, English game entries, and dictionary reference
data. The player loads it separately; grading updates no longer rewrite the large
`replay.json`. Refresh to update squares, the three-color header progress bars,
and annotation background colors together.

Annotated but ungraded characters use hollow squares. Hover to see the annotation
at that moment, the game's reference meaning, the original dictionary entry, and
the grading reason. Playback looks up the raw input of the most recent successful
`note` at that point. Numbers added by the game's display are not graded, and
later annotations do not alter earlier frames.

Regenerating playback data with `prepare.py` also imports grades automatically.
Old grades are ignored when the asset fingerprint differs. Original reference
data stays in the recording directory; entries needed by the player are copied
to `data/grading.json`.

Attach existing grades to the current player without making new API requests:

```powershell
python replay-player/grading/evaluate.py --attach-only
```

Grading another recording does not overwrite the current player. To play it, run:

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python replay-player/prepare.py --recording recordings
```

## Local checks

These checks use temporary recordings and a local mock HTTP endpoint, with no
real API key or external API requests:

```powershell
python -m unittest discover -s replay-player/grading -t replay-player -p test_grading.py -v
node replay-player/tests/test-timeline.mjs
```
