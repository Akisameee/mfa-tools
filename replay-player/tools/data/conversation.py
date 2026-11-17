"""Import public conversation turns and remove only idle waits between turns."""

import re
from datetime import datetime

CONTEXT = re.compile(
    r"<(environment_context|external_[\w-]+)\b[^>]*>.*?</\1>", re.DOTALL
)


def conversation_messages(rows, start, end):
    result, seen = [], set()
    last_assistant = None
    # Thinking before the first tool can exceed the old two-minute margin.
    # Keep the user turn that initiated the recorded work and its public replies.
    preceding_users = []
    for row in rows:
        payload = row.get("payload", {})
        if (row.get("type"), payload.get("type"), payload.get("role")) != (
            "response_item", "message", "user"
        ):
            continue
        at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
        text = "\n".join(
            c.get("text", "") for c in payload.get("content", [])
            if c.get("type") in ("text", "input_text", "output_text")
        )
        if at <= start and CONTEXT.sub("", text).strip():
            preceding_users.append(at)
    lower_bound = min(start - 120, max(preceding_users, default=start - 120))
    for row in rows:
        payload = row.get("payload", {})
        at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
        if not lower_bound <= at <= end + 120:
            continue
        if row.get("type") == "event_msg" and payload.get("type") in (
            "task_complete",
            "turn_aborted",
        ):
            if last_assistant is not None:
                last_assistant["turnEndedAt"] = at
            continue
        role = payload.get("role")
        if (
            row.get("type") != "response_item"
            or payload.get("type") != "message"
            or role not in ("assistant", "user")
        ):
            continue
        channel, phase = payload.get("channel"), payload.get("phase")
        if role == "assistant" and (
            channel not in (None, "commentary", "final")
            or phase not in (None, "commentary", "final", "final_answer")
        ):
            continue
        text = "\n".join(
            c.get("text", "")
            for c in payload.get("content", [])
            if c.get("type") in ("text", "input_text", "output_text")
        ).strip()
        if role == "user":
            text = CONTEXT.sub("", text).strip()
        key = (at, role, text)
        if not text or key in seen:
            continue
        message = {"kind": "message", "role": role, "wall": at, "text": text}
        if role == "assistant" and (
            channel == "final" or phase in ("final", "final_answer")
        ):
            message["phase"] = "final"
        result.append(message)
        seen.add(key)
        last_assistant = message if role == "assistant" else None
    return result


def conversation_compactions(rows, start, end):
    """Import compaction timing only; never export replacement history/summary."""
    result, pending = [], {}
    last_activity, last_completion = None, None
    for row in rows:
        payload = row.get("payload", {})
        at = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp()
        item = payload.get("item", {})
        is_compaction = item.get("type", "").replace("_", "").lower() == "contextcompaction"
        if payload.get("type") == "item_started" and is_compaction:
            pending[item.get("id")] = at
        elif row.get("type") == "compacted" or (payload.get("type") == "item_completed" and is_compaction):
            if last_completion is not None and abs(at - last_completion) < 1:
                pending.pop(item.get("id"), None)
                continue  # SDK may log both a compacted record and a completion item.
            explicit = pending.pop(item.get("id"), None)
            if explicit is None and pending:
                explicit = pending.pop(next(iter(pending)))
            began = explicit if explicit is not None else last_activity
            last_completion, last_activity = at, at
            if began is None or began >= at or not start <= at <= end:
                continue
            call = f"compaction-{len(result) // 2 + 1}"
            timing = "explicit" if explicit is not None else "previous-activity-boundary"
            common = {"tool": "compact_context", "call": call, "source": "codex", "timing": timing}
            result.extend([
                {**common, "kind": "begin", "wall": max(start, began), "args": {}},
                {**common, "kind": "end", "wall": at, "status": "ok", "result": {"completed": True}},
            ])
        elif row.get("type") == "response_item" and payload.get("type") in (
            "message", "custom_tool_call_output", "function_call_output",
        ):
            last_activity = at
    return result


def compact_turn_waits(timeline, network_waits=()):
    """Keep raw milliseconds in real; time is the playhead after idle cuts."""
    candidate, last_activity = None, None
    active_calls, cuts = set(), []
    for event in timeline:
        at = event["wall"]
        if event["kind"] == "message" and event.get("role") == "user":
            if candidate is not None and not active_calls:
                cut_start = max(candidate, last_activity or candidate)
                if cut_start < at:
                    cuts.append((cut_start, at))
            candidate = None
        elif event["kind"] == "message" and event.get("role") == "assistant":
            candidate = (
                at if event.get("phase") == "final" else event.get("turnEndedAt")
            )
        elif event["kind"] == "begin":
            active_calls.add(event["call"])
            if candidate is not None and at > candidate:
                candidate = None  # Work resumed after the reported turn end.
        elif event["kind"] == "end":
            active_calls.discard(event["call"])
        last_activity = at
    origin = timeline[0]["wall"]
    cuts_ms = [
        {"startReal": round((a - origin) * 1000), "endReal": round((b - origin) * 1000)}
        for a, b in cuts
    ]
    # Protect tool execution even if a retry notification overlaps an active call.
    active, protected = {}, []
    for event in timeline:
        if event["kind"] == "begin" and event.get("tool") != "compact_context":
            active[event["call"]] = event["wall"]
        elif event["kind"] == "end" and event["call"] in active:
            protected.append((active.pop(event["call"]), event["wall"]))
    protected.extend((start, timeline[-1]["wall"]) for start in active.values())
    network_cuts = []
    for notice in network_waits:
        parts = [(max(origin, notice["start"]), min(timeline[-1]["wall"], notice["end"]))]
        for a, b in protected:
            parts = [(x, y) for start, end in parts for x, y in
                     ((start, min(end, a)), (max(start, b), end)) if x < y]
            if not parts:
                break
        network_cuts.extend(parts)
    all_cuts = cuts_ms + [
        {"startReal": round((a - origin) * 1000), "endReal": round((b - origin) * 1000)}
        for a, b in network_cuts if a < b
    ]
    merged = []
    for cut in sorted(all_cuts, key=lambda c: c["startReal"]):
        a, b = cut["startReal"], cut["endReal"]
        if merged and a <= merged[-1]["endReal"]:
            merged[-1]["endReal"] = max(b, merged[-1]["endReal"])
        else:
            merged.append({"startReal": a, "endReal": b})
    removed, cursor = 0, 0
    for event in timeline:
        event["real"] = round((event.pop("wall") - origin) * 1000)
        while cursor < len(merged) and merged[cursor]["endReal"] <= event["real"]:
            removed += merged[cursor]["endReal"] - merged[cursor]["startReal"]
            cursor += 1
        partial = max(0, event["real"] - merged[cursor]["startReal"]) if cursor < len(merged) else 0
        event["time"] = event["real"] - removed - partial
        event.pop("turnEndedAt", None)
    return cuts_ms
