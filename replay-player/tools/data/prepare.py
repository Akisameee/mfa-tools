"""Build a private, offline replay bundle from probe logs and visible Codex messages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from .game_catalog import load_catalog
from grading.store import write_playback_grading
from datetime import datetime
from pathlib import Path
from .conversation import conversation_messages, conversation_compactions, compact_turn_waits
from .network_waits import load_network_waits

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent


def read_lines(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # A recorder may still be writing the final line.
    return rows


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def latest_recording():
    root = WORKSPACE / "recordings"
    if (root / "events.jsonl").is_file() and (root / "events.jsonl").stat().st_size:
        return root
    candidates = [
        p
        for p in root.iterdir()
        if (p / "events.jsonl").is_file() and (p / "events.jsonl").stat().st_size
    ]
    if not candidates:
        raise SystemExit("No nonempty recordings found")
    return max(candidates, key=lambda p: p.name)


def find_conversation(start, end):
    database = Path.home() / ".codex/state_5.sqlite"
    if not database.exists():
        return None
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        candidates = list(
            db.execute(
                "SELECT rollout_path, created_at, updated_at FROM threads WHERE cwd LIKE '%MessageFromAliens%'"
            )
        )
    ranked = []
    for path, created, updated in candidates:
        overlap = max(0, min(end, updated) - max(start, created))
        if overlap:
            ranked.append((overlap / max(1, updated - created), overlap, path))
    for _, _, path in sorted(ranked, reverse=True):
        # SQLite can contain escaped extended Windows paths.
        if path.startswith("\\\\?\\"):
            path = path[4:]
        path = path.replace("\\\\", "\\")
        if Path(path).is_file():
            return Path(path)
    return None


def export_glyphs(keys, assets):
    import UnityPy
    from PIL import Image

    output = ROOT / "data"
    cache = output / "glyphs.json"
    fingerprint = hashlib.sha256(assets.read_bytes()).hexdigest()
    shared_assets = assets.parent / "sharedassets0.assets"
    shared_fingerprint = hashlib.sha256(shared_assets.read_bytes()).hexdigest()
    if cache.exists():
        previous = json.loads(cache.read_text(encoding="utf-8"))
        if (
            previous.get("atlasVersion") == 3
            and previous.get("fingerprint") == fingerprint
            and previous.get("sharedFingerprint") == shared_fingerprint
            and set(keys) <= set(previous["items"])
        ):
            return previous
    env = UnityPy.load(str(assets))
    sprites = {}
    for obj in env.objects:
        if obj.type.name == "Sprite":
            name = obj.peek_name()
            if name in keys or name == "notaword":
                sprites[name] = obj
    # Resources.Load also resolves assets held by the scene's shared file.
    # In particular, ResourceManager maps Shapes2D Sprites/0 to that file.
    shared_env = UnityPy.load(str(shared_assets))
    for obj in shared_env.objects:
        if obj.type.name == "Sprite":
            name = obj.peek_name()
            if name in keys and name not in sprites:
                sprites[name] = obj
    missing = sorted(set(keys) - sprites.keys())
    if missing and "notaword" not in sprites:
        raise SystemExit(f"Missing {len(missing)} glyph sprites: {missing[:12]}")
    size, columns = 128, 24
    atlas = Image.new("RGBA", (size * columns, size * math.ceil(len(keys) / columns)))
    items = {}
    for index, key in enumerate(keys):
        # DrawACToSlot uses exactly this fallback when a resource key is absent.
        sprite = sprites.get(key, sprites.get("notaword")).read()
        image = sprite.image.convert("RGBA")
        ratio = min(size / image.width, size / image.height)
        image = image.resize(
            (round(image.width * ratio), round(image.height * ratio)),
            Image.Resampling.LANCZOS,
        )
        # Preserve the asset's alpha, using a single game-like foreground color.
        tinted = Image.new("RGBA", image.size, (233, 217, 169, 255))
        tinted.putalpha(image.getchannel("A"))
        x, y = index % columns * size, index // columns * size
        atlas.alpha_composite(
            tinted, (x + (size - image.width) // 2, y + (size - image.height) // 2)
        )
        items[key] = [x, y, size, size]
    atlas.save(output / "glyphs.png", optimize=True)
    result = {
        "atlasVersion": 3,
        "fingerprint": fingerprint,
        "sharedFingerprint": shared_fingerprint,
        "atlas": "data/glyphs.png",
        "items": items,
        "fallbackKeys": missing,
    }
    cache.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def prepare(recording, conversation, assets):
    catalog = load_catalog(assets)
    events = read_lines(recording / "events.jsonl")
    first, last = epoch(events[0]["at"]), epoch(events[-1]["at"])
    if conversation is None:
        conversation = find_conversation(first, last)
    conversation_rows = read_lines(conversation) if conversation else []
    messages = conversation_messages(conversation_rows, first, last)
    network_waits = load_network_waits(conversation_rows, recording, conversation, ROOT / "data") if conversation else []
    starts, states, state_indices, keys = {}, [], {}, []
    key_set, notes, completed = set(), {}, set()
    timeline = []
    last_snapshot = None
    mouse = [12, 6.5]
    completable = set(catalog["questions"] + catalog["games"] + catalog["texts"])
    for event in events:
        common = {
            "wall": epoch(event["at"]),
            "seq": event["seq"],
            "call": event["call_id"],
        }
        if event["kind"] == "call.begin":
            starts[event["call_id"]] = event
            item = {
                **common,
                "kind": "begin",
                "tool": event["tool"],
                "args": event["arguments"],
            }
            if event["tool"] == "glyph":
                item["focus"] = {"page": (last_snapshot or {}).get("page")}
            if event["tool"] in ("click", "note"):
                args = event["arguments"]
                cells = last_snapshot["cells"] if last_snapshot else []
                key = next(
                    (
                        key
                        for key, value in (last_snapshot or {}).get("ids", {}).items()
                        if value == args.get("hash")
                    ),
                    None,
                )
                matches = [c for c in cells if c["word"] == key]
                cell = (
                    min(
                        matches,
                        key=lambda c: (
                            (c["col"] + 0.5 - mouse[0]) ** 2
                            + (c["row"] * 1.5 + 1.25 - mouse[1]) ** 2
                        ),
                    )
                    if matches
                    else None
                )
                target = (
                    [args["col"] + 0.5, args["row"] * 1.5 + 0.55]
                    if event["tool"] == "click"
                    else (
                        [cell["col"] + 0.5, cell["row"] * 1.5 + 1.25]
                        if cell
                        else [20.5, 11.9]
                    )
                )
                item["motion"] = {
                    "from": mouse,
                    "page": (last_snapshot or {}).get("page"),
                    "target": target,
                    "key": key,
                    "cell": [cell["row"], cell["col"]] if cell else None,
                    "floating": event["tool"] == "note" and cell is None,
                    "oldText": cell.get("note", "?") if cell else "",
                }
                mouse = target
            timeline.append(item)
            continue
        reference = event.get("state_ref")
        state_index = None
        updates = {}
        if reference:
            if reference not in state_indices:
                snapshot = json.loads(
                    (recording / reference).read_text(encoding="utf-8")
                )["snapshot"]
                state_indices[reference] = len(states)
                states.append(snapshot)
            state_index = state_indices[reference]
            snapshot = states[state_index]
            last_snapshot = snapshot
            if event.get("state_observed"):
                for cell in snapshot["cells"]:
                    key, note = cell["word"], cell.get("note") or "?"
                    if key not in key_set:
                        keys.append(key)
                        key_set.add(key)
                    if notes.get(key, "?") != note:
                        notes[key] = note
                        updates[key] = note
                if snapshot["page"] in completable and any(
                    c["word"] == "win" and c["row"] == 0 and c["col"] >= 12
                    for c in snapshot["cells"]
                ):
                    completed.add(snapshot["page"])
                # Draw renders a menu's (win) marker by dimming the linked row.
                # Match only complete, underlined links to known page keys.
                menu_rows = {}
                for cell in snapshot["cells"]:
                    if cell.get("block") == "right_text_down":
                        menu_rows.setdefault(cell["row"], []).append(cell)
                for row in menu_rows.values():
                    row.sort(key=lambda c: c["col"])
                    target = " ".join(c["word"] for c in row)
                    if target in completable and all(
                        c.get("dim") and c.get("underlined") for c in row
                    ):
                        completed.add(target)
        start = starts.get(event["call_id"], {})
        character = event.get("character")
        if event["tool"] == "note" and event["status"] == "ok" and character:
            key, note = (
                character["key"],
                start.get("arguments", {}).get("text", "") or "?",
            )
            if key not in key_set:
                keys.append(key)
                key_set.add(key)
            notes[key] = note
            updates[key] = note
        timeline.append(
            {
                **common,
                "kind": "end",
                "tool": event["tool"],
                "state": state_index,
                "observed": event.get("state_observed", False),
                "capture": event.get("capture"),
                "updates": updates,
                "completed": len(completed),
                "progress": {
                    "questions": [
                        key for key in catalog["questions"] if key in completed
                    ],
                    "games": [key for key in catalog["games"] if key in completed],
                    "texts": [key for key in catalog["texts"] if key in completed],
                },
                "status": event["status"],
                "error": event.get("error"),
                "character": character,
                "result": event.get("result"),
            }
        )
    timeline += messages
    compactions = conversation_compactions(conversation_rows, first, last)
    timeline += compactions
    timeline.sort(key=lambda e: (e["wall"], e.get("seq", -1)))
    before_network = [dict(event) for event in timeline]
    compact_turn_waits(before_network)
    idle_cuts = compact_turn_waits(timeline, network_waits)
    network_removed = before_network[-1]["time"] - timeline[-1]["time"]
    begin_events = {e["call"]: e for e in timeline if e["kind"] == "begin"}
    for event in timeline:
        if event["kind"] == "end" and event["call"] in begin_events:
            begin_events[event["call"]]["endTime"] = event["time"]
            begin_events[event["call"]]["endReal"] = event["real"]
            if event.get("character") and begin_events[event["call"]].get("motion"):
                begin_events[event["call"]]["motion"]["key"] = event["character"]["key"]
            if event.get("character") and event["tool"] == "glyph":
                begin_events[event["call"]]["focus"]["key"] = event["character"]["key"]
    output = ROOT / "data"
    output.mkdir(exist_ok=True)
    glyphs = export_glyphs(keys, assets)
    bundle = {
        "version": 3,
        "recording": recording.name,
        "events": timeline,
        "states": states,
        "keys": keys,
        "catalog": catalog,
        "glyphs": glyphs,
        "gradingFile": "data/grading.json",
        "messages": len(messages),
        "compactions": len(compactions) // 2,
        "assistantMessages": sum(m.get("role") == "assistant" for m in messages),
        "userMessages": sum(m.get("role") == "user" for m in messages),
        "idleCuts": idle_cuts,
        "networkWaits": {"notices": network_waits, "removedMs": network_removed, "policy": "failed-request-wait-and-retry-backoff", "boundary": "previous-transcript-activity"},
        "duration": timeline[-1]["time"],
        "realDuration": timeline[-1]["real"],
        "progressDefinition": "Reading texts, questions, and games use recorded title win markers and dimmed (win) menu links. Words use observed historical annotations, excluding tokens and aliases. Unobserved save progress is unknown. Source recordings are read-only.",
    }
    (output / "replay.json").write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    write_playback_grading(recording, output, glyphs["fingerprint"])
    print(
        f"Prepared {len(starts)} calls, {len(messages)} public messages, {len(states)} states, {len(keys)} glyphs, {len(completed)} observed cleared pages"
    )
    print(f"Source conversation: {conversation}")
    print(f"Network retry records: {len(network_waits)}; removed request waits and backoff: {network_removed / 1000:.3f}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path)
    parser.add_argument("--conversation", type=Path)
    parser.add_argument(
        "--assets",
        type=Path,
        default=Path(
            r"E:\Software\Steam\steamapps\common\Message From Aliens\MessageFromAliens_Data\resources.assets"
        ),
    )
    args = parser.parse_args()
    prepare(args.recording or latest_recording(), args.conversation, args.assets)
