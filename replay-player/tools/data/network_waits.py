"""Align logged failures and retry backoffs with transcript activity boundaries."""

from datetime import datetime
from bisect import bisect_right
from pathlib import Path
import re

RETRY = re.compile(r"codex_core::responses_retry:.*?turn_id=([\w-]+)")
DELAY = re.compile(r"retry_delay=(\d+(?:\.\d+)?)(ms|s)\b")
SAMPLING = re.compile(r"retrying sampling request \(\d+/\d+ in (\d+(?:\.\d+)?)(ms|s)\)")


def retry_waits(lines, turn_ids, zone):
    notices = {}
    for line in lines:
        match = RETRY.search(line)
        if not match or match[1] not in turn_ids:
            continue
        delay = DELAY.search(line) or SAMPLING.search(line)
        if delay is None:
            continue
        at = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=zone).timestamp()
        seconds = float(delay[1]) / (1000 if delay[2] == "ms" else 1)
        item = {"start": at, "end": at + seconds, "turnId": match[1]}
        notices[(at, seconds, match[1])] = item
    return sorted(notices.values(), key=lambda item: item["start"])


def include_failed_requests(notices, conversation_rows):
    """Align a failed attempt to the preceding transcript activity boundary.

    These are transcript boundaries, not packet-level request start times. Never
    use token_count: it can be emitted by error handling just before a timeout.
    Inspect event types/timestamps only, including progress-item timestamps.
    """
    activity = []
    for row in conversation_rows:
        payload = row.get("payload", {})
        boundary = (
            row.get("type") == "response_item" and payload.get("type") in (
                "message", "reasoning", "custom_tool_call", "custom_tool_call_output",
                "function_call", "function_call_output", "configuration_update",
            )
        ) or (row.get("type") == "event_msg" and payload.get("type") in ("task_started", "user_message"))
        if boundary and row.get("timestamp"):
            activity.append(datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")).timestamp())
    activity.sort()
    result, previous_end = [], float("-inf")
    for notice in sorted(notices, key=lambda n: n["start"]):
        at = notice["start"]
        index = bisect_right(activity, at)
        start = max(activity[index - 1], previous_end) if index else at
        start = min(at, start)
        result.append({**notice, "retryAt": at, "start": start,
                       "requestWaitMs": round((at - start) * 1000),
                       "boundary": "previous-transcript-activity" if start < at else "retry-log"})
        previous_end = max(previous_end, notice["end"])
    return result


def load_network_waits(conversation_rows, recording, conversation, output):
    import json

    turn_ids = {
        row["payload"]["turn_id"] for row in conversation_rows
        if (row.get("type") == "turn_context" or
            (row.get("type") == "event_msg" and row.get("payload", {}).get("type") == "task_started"))
        and row.get("payload", {}).get("turn_id")
    }
    source = {"recording": str(recording.resolve()), "conversation": str(conversation.resolve())}
    zone = datetime.now().astimezone().tzinfo
    lines = []
    logs = Path.home() / "AppData/Roaming/Code/logs"
    for path in logs.glob("*/window*/exthost/openai.chatgpt/Codex*.log"):
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    notices = retry_waits(lines, turn_ids, zone)
    cache = output / "network-waits.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("source") == source:
            combined = {(n["start"], n["end"], n["turnId"]): n for n in saved["notices"] + notices}
            notices = sorted(combined.values(), key=lambda n: n["start"])
    output.mkdir(exist_ok=True)
    cache.write_text(json.dumps({"version": 1, "source": source, "policy": "explicit-retry-backoff-only", "notices": notices}, indent=2), encoding="utf-8")
    return include_failed_requests(notices, conversation_rows)
