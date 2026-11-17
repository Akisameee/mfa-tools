import _paths  # noqa: F401
"""Retry-log alignment must not remove thinking, tools, or the same time twice."""

from datetime import timezone, timedelta
import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from tools.data.conversation import compact_turn_waits
from tools.data.network_waits import retry_waits, load_network_waits, include_failed_requests


def message(at, role="assistant", **extra):
    return {"kind": "message", "wall": at, "role": role, **extra}


class NetworkWaitTests(unittest.TestCase):
    def test_failed_attempts_start_after_previous_activity_or_backoff(self):
        rows = [{"timestamp": "1970-01-01T00:00:00Z", "type": "response_item",
                 "payload": {"type": "message"}}]
        notices = [{"start": 15, "end": 16}, {"start": 31, "end": 33}]
        waits = include_failed_requests(notices, rows)
        self.assertEqual([n["start"] for n in waits], [0, 16])
        self.assertEqual([n["requestWaitMs"] for n in waits], [15000, 15000])

    def test_sse_timeout_uses_last_progress_ignoring_error_token_count(self):
        rows = [
            {"timestamp": "1970-01-01T00:00:05Z", "type": "response_item", "payload": {"type": "custom_tool_call_output"}},
            {"timestamp": "1970-01-01T00:00:20Z", "type": "response_item", "payload": {"type": "reasoning"}},
            {"timestamp": "1970-01-01T00:05:19Z", "type": "event_msg", "payload": {"type": "token_count"}},
        ]
        waits = include_failed_requests([{"start": 320, "end": 321}], rows)
        self.assertEqual(waits[0]["start"], 20)
        self.assertEqual(waits[0]["requestWaitMs"], 300000)
        events = [message(0, "user"), message(5), message(20), message(330)]
        compact_turn_waits(events, waits)
        self.assertEqual([e["time"] for e in events], [0, 5000, 20000, 29000])

    def test_rotated_logs_and_task_started_turn_ids_are_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "AppData/Roaming/Code/logs/session/window1/exthost/openai.chatgpt"
            logs.mkdir(parents=True)
            logfile = logs / "Codex.1.log"
            logfile.write_text('1970-01-01 08:00:02.000 [warning] codex_core::responses_retry: stream connection failed; waiting to retry turn_id=game retry_delay=5s\n')
            rows = [{"type": "event_msg", "payload": {"type": "task_started", "turn_id": "game"}}]
            output = root / "data"
            with patch("tools.data.network_waits.Path.home", return_value=root):
                found = load_network_waits(rows, root, root / "conversation.jsonl", output)
                self.assertEqual(len(found), 1)
                logfile.unlink()
                cached = load_network_waits(rows, root, root / "conversation.jsonl", output)
                self.assertEqual(cached, found)

    def test_only_matching_turn_retry_notices_and_explicit_backoffs(self):
        lines = [
            '1970-01-01 08:00:02.000 [warning] codex_core::responses_retry: stream connection failed; waiting to retry turn_id=game retry_delay=5s',
            '1970-01-01 08:00:10.000 [warning] codex_core::responses_retry: stream disconnected - retrying sampling request (1/5 in 193ms)... turn_id=game sampling_error=request timed out',
            '1970-01-01 08:00:20.000 [warning] codex_core::responses_retry: stream connection failed; waiting to retry turn_id=other retry_delay=10s',
            '1970-01-01 08:00:30.000 [warning] codex_analytics::client: request failed turn_id=game retry_delay=10s',
        ]
        result = retry_waits(lines + lines, {"game"}, timezone(timedelta(hours=8)))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], {"start": 2, "end": 7, "turnId": "game"})
        self.assertAlmostEqual(result[1]["end"], 10.193)

    def test_only_backoff_is_removed_with_monotonic_times_inside_cut(self):
        events = [message(0, "user"), message(5), message(10)]
        compact_turn_waits(events, [{"start": 3, "end": 7}])
        self.assertEqual([e["time"] for e in events], [0, 3000, 6000])
        self.assertEqual([e["real"] for e in events], [0, 5000, 10000])

    def test_tools_are_protected_from_overlapping_backoff(self):
        events = [message(0, "user"), {"kind": "begin", "wall": 4, "call": "a"},
                  {"kind": "end", "wall": 6, "call": "a"}, message(10)]
        compact_turn_waits(events, [{"start": 2, "end": 8}])
        self.assertEqual([e["time"] for e in events], [0, 2000, 4000, 6000])

    def test_overlapping_network_and_between_turn_cuts_are_not_double_counted(self):
        events = [message(0, "user"), message(2, phase="final"), message(100, "user"), message(103)]
        compact_turn_waits(events, [{"start": 5, "end": 10}, {"start": 6, "end": 12}])
        self.assertEqual(events[-1]["time"], 5000)

    def test_incomplete_tools_and_out_of_range_notices(self):
        events = [message(0, "user"), {"kind": "begin", "wall": 4, "call": "a"}, message(10)]
        compact_turn_waits(events, [{"start": 5, "end": 9}, {"start": -10, "end": -5}, {"start": 11, "end": 20}])
        self.assertEqual(events[-1]["time"], 10000)


if __name__ == "__main__":
    unittest.main()
