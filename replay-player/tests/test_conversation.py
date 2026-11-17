import _paths  # noqa: F401
"""Conversation import and between-turn cuts, without game assets or a save."""

import unittest
from tools.data.conversation import conversation_messages, conversation_compactions, compact_turn_waits


def message(wall, role, **extra):
    return {"kind": "message", "wall": wall, "role": role, "text": role, **extra}


class ConversationTests(unittest.TestCase):
    def test_compaction_uses_activity_boundary_and_never_exports_summary(self):
        rows = [
            {"timestamp":"1970-01-01T00:00:02Z", "type":"response_item", "payload":{"type":"custom_tool_call_output"}},
            {"timestamp":"1970-01-01T00:00:19Z", "type":"token_usage_record", "payload":{}},
            {"timestamp":"1970-01-01T00:00:20Z", "type":"compacted", "payload":{"message":"PRIVATE SUMMARY", "replacement_history":["PRIVATE HISTORY"]}},
            {"timestamp":"1970-01-01T00:00:20.05Z", "type":"event_msg", "payload":{"type":"item_completed", "item":{"type":"ContextCompaction","id":"c"}}},
        ]
        events = conversation_compactions(rows, 0, 30)
        self.assertEqual([e["wall"] for e in events], [2,20])
        self.assertEqual(events[0]["timing"], "previous-activity-boundary")
        self.assertNotIn("PRIVATE", str(events))

    def test_explicit_compaction_start_is_preferred(self):
        rows = [
            {"timestamp":"1970-01-01T00:00:01Z", "type":"response_item", "payload":{"type":"custom_tool_call_output"}},
            {"timestamp":"1970-01-01T00:00:05Z", "type":"event_msg", "payload":{"type":"item_started", "item":{"type":"ContextCompaction","id":"c"}}},
            {"timestamp":"1970-01-01T00:00:20Z", "type":"event_msg", "payload":{"type":"item_completed", "item":{"type":"ContextCompaction","id":"c"}}},
        ]
        events = conversation_compactions(rows, 0, 30)
        self.assertEqual(events[0]["wall"], 5)
        self.assertEqual(events[0]["timing"], "explicit")

    def test_opening_user_turn_survives_long_thinking_before_first_tool(self):
        rows = [
            {"timestamp": "1970-01-01T00:00:00Z", "type": "response_item",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "Play the game"}]}},
            {"timestamp": "1970-01-01T00:00:05Z", "type": "response_item",
             "payload": {"type": "message", "role": "assistant", "channel": "commentary",
                         "content": [{"type": "output_text", "text": "Starting"}]}},
            {"timestamp": "1970-01-01T00:02:00Z", "type": "response_item",
             "payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "<environment_context>injected</environment_context>"}]}},
        ]
        imported = conversation_messages(rows, 180, 200)
        self.assertEqual([m["text"] for m in imported], ["Play the game", "Starting"])

    def test_quota_completion_without_final_marks_last_public_message(self):
        rows = [
            {
                "timestamp": "1970-01-01T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "working"}],
                },
            },
            {
                "timestamp": "1970-01-01T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "task_complete", "last_agent_message": None},
            },
        ]
        imported = conversation_messages(rows, 0, 10)
        self.assertEqual(imported[0]["turnEndedAt"], 2)
        self.assertNotIn("phase", imported[0])

    def test_imports_user_and_public_final_without_injected_context(self):
        def row(second, role, text, **extra):
            return {
                "timestamp": f"1970-01-01T00:00:{second:02d}Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": role,
                    "content": [
                        {
                            "type": "input_text" if role == "user" else "output_text",
                            "text": text,
                        }
                    ],
                    **extra,
                },
            }

        rows = [
            row(
                0, "user", "<environment_context>private context</environment_context>"
            ),
            row(
                1, "user", "<external_ide_context>file list</external_ide_context>继续"
            ),
            row(2, "assistant", "hidden", channel="analysis"),
            row(3, "assistant", "done", phase="final_answer"),
        ]
        imported = conversation_messages(rows, 0, 20)
        self.assertEqual(
            [(m["role"], m["text"]) for m in imported],
            [("user", "继续"), ("assistant", "done")],
        )
        self.assertEqual(imported[1]["phase"], "final")

    def test_final_wait_removed_but_next_thinking_retained(self):
        events = [
            message(0, "user"),
            message(2, "assistant", phase="final"),
            message(100, "user"),
            message(103, "assistant"),
        ]
        cuts = compact_turn_waits(events)
        self.assertEqual(cuts, [{"startReal": 2000, "endReal": 100000}])
        self.assertEqual([e["time"] for e in events], [0, 2000, 2000, 5000])
        self.assertEqual(events[2]["real"], 100000)

    def test_quota_stop_without_final_keeps_remaining_tools(self):
        events = [
            message(0, "user"),
            message(1, "assistant", turnEndedAt=4),
            {"kind": "begin", "wall": 2, "call": "a"},
            {"kind": "end", "wall": 3, "call": "a"},
            message(100, "user"),
        ]
        cuts = compact_turn_waits(events)
        self.assertEqual(cuts, [{"startReal": 4000, "endReal": 100000}])
        self.assertEqual(events[-1]["time"], 4000)
        self.assertEqual(events[3]["time"] - events[2]["time"], 1000)

    def test_active_user_interruption_and_normal_thinking_are_not_cut(self):
        for events in [
            [message(0, "user"), message(1, "assistant"), message(10, "user")],
            [
                message(0, "user"),
                message(1, "assistant", phase="final"),
                {"kind": "begin", "wall": 2, "call": "a"},
                message(3, "user"),
                {"kind": "end", "wall": 4, "call": "a"},
            ],
        ]:
            self.assertEqual(compact_turn_waits(events), [])
            self.assertTrue(all(e["time"] == e["real"] for e in events))


if __name__ == "__main__":
    unittest.main()
