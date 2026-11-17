"""Grade recorded annotations using a configurable Chat Completions API."""

from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grading.reference import DEFAULT_ASSETS, extract_reference, reference_for  # noqa: E402
from grading.store import (  # noqa: E402
    GRADES,
    annotation_versions,
    append_jsonl,
    atomic_json,
    attach_grading,
    digest,
    now,
    successful_scores,
)


class FatalAPIError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def load_config(path):
    if not path.exists():
        raise ValueError(
            f"Configuration not found: {path}. Copy config.example.toml first."
        )
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    for name in ("base_url", "model"):
        config[name] = os.environ.get(
            "GRADING_" + name.upper(), config.get(name, "")
        ).strip()
    config["api_key"] = os.environ.get(
        config.get("api_key_env", "GRADING_API_KEY"), config.get("api_key", "")
    ).strip()
    for name, default in (
        ("batch_size", 12),
        ("concurrency", 2),
        ("retry_attempts", 3),
    ):
        value = config.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
        config[name] = value
    config.setdefault("timeout_seconds", 120)
    if config["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be positive")
    config.setdefault("json_mode", True)
    config.setdefault("request", {})
    if set(config["request"]) & {"model", "messages", "stream", "n"}:
        raise ValueError(
            "request parameters cannot override model, messages, stream, or n"
        )
    return config


def validate_api(config):
    for field in ("base_url", "model", "api_key"):
        if not config.get(field):
            raise ValueError(
                f"Configure {field} in grading/config.toml or its environment variable"
            )
    url = urlsplit(config["base_url"])
    if (
        url.scheme not in ("https", "http")
        or not url.netloc
        or url.username
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "base_url must be an HTTP(S) URL without credentials, query, or fragment"
        )


def validate_response(content, items):
    if not isinstance(content, str):
        raise ValueError("The API returned no text content")
    if content.strip().startswith("```"):
        lines = content.strip().splitlines()
        content = "\n".join(lines[1:-1])
    payload = json.loads(content)
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Response must be a JSON object containing a results array")
    expected = {item["id"] for item in items}
    found, result = set(), []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("id") not in expected
            or row["id"] in found
        ):
            raise ValueError("Response has an unknown or duplicate item id")
        if (
            row.get("grade") not in GRADES
            or not isinstance(row.get("reason"), str)
            or not row["reason"].strip()
        ):
            raise ValueError("Each result needs a valid grade and a nonempty reason")
        found.add(row["id"])
        result.append(
            {"id": row["id"], "grade": row["grade"], "reason": row["reason"].strip()}
        )
    if found != expected:
        raise ValueError("Response omitted requested item ids")
    return result


def grade_batch(config, prompt, notation, items):
    url = config["base_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = {
        **config["request"],
        "model": config["model"],
        "stream": False,
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "notation": notation,
                        "items": [
                            {
                                name: item[name]
                                for name in ("id", "annotation", "reference")
                            }
                            for item in items
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    if config["json_mode"] and "response_format" not in payload:
        payload["response_format"] = {"type": "json_object"}
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={
            "Authorization": "Bearer " + config["api_key"],
            "Content-Type": "application/json",
            "User-Agent": "MessageFromAliens-local-grading/1",
        },
    )
    last_error = ""
    for attempt in range(config["retry_attempts"]):
        try:
            with build_opener(NoRedirect()).open(
                request, timeout=config["timeout_seconds"]
            ) as response:
                body = json.load(response)
            choice = body["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError(
                    "Model output was truncated; reduce batch_size or increase the output token limit"
                )
            result = validate_response(choice["message"].get("content"), items)
            return result, body.get("usage", {})
        except HTTPError as error:
            detail = (
                error.read(1500)
                .decode("utf-8", errors="replace")
                .replace(config["api_key"], "[redacted]")
            )
            error.close()
            last_error = f"HTTP {error.code}: {detail}"
            if error.code != 429 and error.code < 500:
                raise FatalAPIError(last_error) from None
        except (
            URLError,
            TimeoutError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            last_error = str(error).replace(config["api_key"], "[redacted]")
        if attempt + 1 < config["retry_attempts"]:
            time.sleep(min(10, 2**attempt))
    raise RuntimeError(last_error)


def default_recording():
    bundle = ROOT / "data" / "replay.json"
    if bundle.exists():
        name = json.loads(bundle.read_text(encoding="utf-8"))["recording"]
        root = ROOT.parent / "recordings"
        return root if name == root.name else root / name
    root = ROOT.parent / "recordings"
    if (root / "events.jsonl").is_file() and (root / "events.jsonl").stat().st_size:
        return root
    candidates = [
        p
        for p in (ROOT.parent / "recordings").iterdir()
        if (p / "events.jsonl").is_file() and (p / "events.jsonl").stat().st_size
    ]
    if not candidates:
        raise ValueError("No recording found; pass --recording PATH")
    return max(candidates, key=lambda p: p.name)


def run(args):
    recording = (args.recording or default_recording()).resolve()
    if not (recording / "events.jsonl").is_file():
        raise ValueError(f"No events.jsonl in {recording}")
    bundle_path = args.bundle.resolve()
    if args.attach_only:
        if not attach_grading(recording, bundle_path):
            raise ValueError(
                "Bundle is missing or belongs to a different recording; run prepare.py for this recording"
            )
        print(f"Updated playback grading: {bundle_path.parent / 'grading.json'}")
        return 0
    config = load_config(args.config)
    if not args.prepare_only:
        validate_api(config)
    directory = recording / "grading"
    fingerprint = hashlib.sha256(args.assets.read_bytes()).hexdigest()
    reference_path = directory / "reference.json"
    reference = (
        json.loads(reference_path.read_text(encoding="utf-8"))
        if reference_path.exists()
        else None
    )
    if (
        not reference
        or reference.get("version") != 1
        or reference.get("assets_fingerprint") != fingerprint
    ):
        reference = {"version": 1, **extract_reference(args.assets)}
        atomic_json(reference_path, reference)
    versions = annotation_versions(recording)
    prompt = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")
    context = digest(
        {
            "reference": digest(reference),
            "pipeline_version": 2,
            "prompt": prompt,
            "model": config["model"],
            "base_url": config["base_url"].rstrip("/"),
            "json_mode": config["json_mode"],
            "request": config["request"],
        }
    )
    items = [
        {
            "id": digest(
                {
                    "context": context,
                    "key": version["key"],
                    "annotation": version["annotation"],
                }
            ),
            **version,
            "reference": reference_for(reference, version["key"]),
        }
        for version in versions
    ]
    atomic_json(directory / "items.json", items)
    print(f"Recording: {recording.name}")
    print(
        f"Annotation versions: {len(items)}; missing dictionary entries: {sum(i['reference'] is None for i in items)}"
    )
    if args.prepare_only:
        print(f"Prepared references and items in {directory}; no API requests made.")
        return 0
    cached = successful_scores(directory, context)
    pending = [
        item
        for item in items
        if item["id"] not in cached
        or (args.retry_unresolved and cached[item["id"]]["grade"] == "unresolved")
    ]
    if args.limit:
        pending = pending[: args.limit]
    metadata = {
        "version": 1,
        "context": context,
        "model": config["model"],
        "base_url": config["base_url"],
        "assets_fingerprint": fingerprint,
        "reference_sha256": digest(reference),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "versions": len(items),
        "annotation_source": "successful note.arguments.text",
        "recording": recording.name,
        "updated_at": now(),
    }
    atomic_json(directory / "metadata.json", metadata)
    by_id = {item["id"]: item for item in items}

    def save(rows):
        for row in rows:
            item = by_id[row["id"]]
            entry = {
                **row,
                "key": item["key"],
                "annotation": item["annotation"],
                "context": context,
                "model": config["model"],
                "at": now(),
            }
            append_jsonl(directory / "scores.jsonl", entry)
            cached[row["id"]] = entry

    missing = [item for item in pending if item["reference"] is None]
    save(
        [
            {
                "id": item["id"],
                "grade": "unresolved",
                "reason": "游戏资源中未找到此字符的字典资料，保留待核对。",
            }
            for item in missing
        ]
    )
    pending = [item for item in pending if item["reference"] is not None]
    batches = [
        pending[i : i + config["batch_size"]]
        for i in range(0, len(pending), config["batch_size"])
    ]
    print(f"Cached: {len(cached)}; API batches this run: {len(batches)}")
    failed = 0
    try:
        with ThreadPoolExecutor(max_workers=config["concurrency"]) as executor:
            remaining = iter(batches)
            active = {}

            def submit():
                batch = next(remaining, None)
                if batch is not None:
                    future = executor.submit(
                        grade_batch, config, prompt, reference["notation"], batch
                    )
                    active[future] = batch

            for _ in range(config["concurrency"]):
                submit()
            while active:
                done, _ = wait(active, return_when=FIRST_COMPLETED)
                fatal = False
                for future in done:
                    batch = active.pop(future)
                    try:
                        rows, usage = future.result()
                        save(rows)
                        append_jsonl(
                            directory / "requests.jsonl",
                            {
                                "at": now(),
                                "context": context,
                                "ids": [i["id"] for i in batch],
                                "usage": usage,
                            },
                        )
                        print(
                            f"Saved {len(rows)} results; cached {len(cached)} / {len(items)}",
                            flush=True,
                        )
                    except Exception as error:
                        failed += len(batch)
                        detail = str(error).replace(config["api_key"], "[redacted]")
                        append_jsonl(
                            directory / "errors.jsonl",
                            {
                                "at": now(),
                                "context": context,
                                "ids": [i["id"] for i in batch],
                                "error": detail,
                            },
                        )
                        print(
                            f"Batch failed ({len(batch)} items remain pending): {detail}",
                            file=sys.stderr,
                            flush=True,
                        )
                        fatal |= isinstance(error, FatalAPIError)
                if fatal:
                    for future in active:
                        future.cancel()
                    break
                for _ in done:
                    submit()
    finally:
        metadata["updated_at"] = now()
        metadata["scored"] = sum(r["grade"] != "unresolved" for r in cached.values())
        metadata["unresolved"] = sum(
            r["grade"] == "unresolved" for r in cached.values()
        )
        atomic_json(directory / "metadata.json", metadata)
        if attach_grading(recording, bundle_path):
            print(f"Playback grading updated: {bundle_path.parent / 'grading.json'}")
        else:
            print(
                "Scores saved. Run prepare.py --recording with this recording to display them."
            )
    print(f"Saved to: {directory}")
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).parent / "config.toml"
    )
    parser.add_argument(
        "--recording",
        type=Path,
        help="Defaults to the recording currently loaded by the player",
    )
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--bundle", type=Path, default=ROOT / "data" / "replay.json")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Extract references and annotation versions without API requests",
    )
    parser.add_argument(
        "--attach-only",
        action="store_true",
        help="Attach existing scores to the matching playback bundle",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum uncached versions to grade this run (0 = all)",
    )
    parser.add_argument(
        "--retry-unresolved",
        action="store_true",
        help="Ask the model again about cached unresolved results",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    try:
        return run(args)
    except KeyboardInterrupt:
        print(
            "Interrupted; saved results will be reused on the next run.",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
