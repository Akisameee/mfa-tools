"""Read recorded annotation versions and persist independent grading files."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import tempfile
from datetime import datetime, timezone
from pathlib import Path

GRADES = {"correct", "partial", "wrong", "unresolved"}


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def normalize(text):
    return unicodedata.normalize("NFC", text).strip()


def known(text):
    return bool(text and normalize(text) not in ("", "?"))


def now():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path):
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise ValueError(
                    f"Invalid JSON on line {index + 1} of {path}"
                ) from None
            # An interrupted append may leave a final partial line.


def atomic_json(path, value, *, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    options = {"separators": (",", ":")} if compact else {"indent": 2}
    # Distinct temporary files also keep two writers from replacing each other's
    # pending output.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=path.name + ".", suffix=".tmp", delete=False,
    ) as stream:
        json.dump(value, stream, ensure_ascii=False, **options)
        temporary = Path(stream.name)
    temporary.replace(path)


def append_jsonl(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Repair an interrupted final entry before appending: leaving it as a
    # malformed middle line would prevent the next resume from reading it.
    if path.exists() and path.stat().st_size:
        with path.open("rb+") as handle:
            data = handle.read()
            if not data.endswith(b"\n"):
                start = data.rfind(b"\n") + 1
                try:
                    json.loads(data[start:])
                except (json.JSONDecodeError, UnicodeDecodeError):
                    handle.truncate(start)
                else:
                    handle.seek(0, 2)
                    handle.write(b"\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        )
        handle.flush()


def annotation_versions(recording):
    """Grade successful note inputs only; never read rendered snapshot text."""
    starts, versions = {}, {}
    for event in read_jsonl(recording / "events.jsonl"):
        if event["kind"] == "call.begin" and event.get("tool") == "note":
            starts[event["call_id"]] = event.get("arguments", {})
            continue
        if (
            event.get("tool") == "note"
            and event.get("status") == "ok"
            and event.get("character")
        ):
            key = event["character"]["key"]
            text = starts.get(event["call_id"], {}).get("text")
            if key and isinstance(text, str) and known(text):
                annotation = normalize(text)
                versions.setdefault(
                    (key, annotation), {"key": key, "annotation": annotation}
                )
    return list(versions.values())


def successful_scores(directory, context):
    result = {}
    for row in read_jsonl(directory / "scores.jsonl"):
        if row.get("context") == context and row.get("grade") in GRADES:
            result[row["id"]] = row
    return result


def load_grading(recording, assets_fingerprint=None):
    """Build the playback lookup and original author references for hover comparison."""
    directory = recording / "grading"
    manifest = directory / "metadata.json"
    if not manifest.exists():
        return None
    metadata = json.loads(manifest.read_text(encoding="utf-8"))
    if assets_fingerprint and metadata.get("assets_fingerprint") != assets_fingerprint:
        print("Grading ignored: the game assets differ from the grading reference.")
        return None
    scores = successful_scores(directory, metadata["context"])
    lookup = {}
    for row in scores.values():
        lookup.setdefault(row["key"], {})[row["annotation"]] = {
            "grade": row["grade"],
            "reason": row["reason"],
        }
    if not lookup:
        return None
    from .reference import reference_for

    references = {}
    reference_path = directory / "reference.json"
    if reference_path.exists():
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        if reference.get("assets_fingerprint") == metadata.get("assets_fingerprint"):
            references = {
                key: entry for key in lookup
                if (entry := reference_for(reference, key)) is not None
            }
    return {
        "model": metadata["model"],
        "context": metadata["context"],
        "lookup": lookup,
        "references": references,
        "versions": len(scores),
        "expectedVersions": metadata["versions"],
    }


def attach_grading(recording, bundle_path):
    if not bundle_path.exists():
        return False
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("recording") != recording.name:
        return False
    write_playback_grading(recording, bundle_path.parent, bundle.get("glyphs", {}).get("fingerprint"))
    return True


def write_playback_grading(recording, output, assets_fingerprint):
    atomic_json(output / "grading.json", {
        "version": 1,
        "recording": recording.name,
        "assetsFingerprint": assets_fingerprint,
        "grading": load_grading(recording, assets_fingerprint),
    }, compact=True)
