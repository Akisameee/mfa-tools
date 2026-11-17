"""Synthetic game for exercising the production MCP probe over stdio."""

from unittest.mock import Mock

from aliens_mcp import tools
from aliens_mcp.server import run

visible = {"note": "initial"}
client = Mock(alive=True, pid=1)
client.vocabulary.return_value = ["test-character"]
client.snapshot.side_effect = lambda: {
    "page": "fixture",
    "rows": 9,
    "cols": 24,
    "cells": [
        {
            "row": 1,
            "col": 2,
            "word": "test-character",
            "block": "right_text_down",
            "note": visible["note"],
            "underlined": True,
            "highlight": False,
            "dim": False,
        }
    ],
    "frames": [],
    "boxes": [],
    "geometry": {"center_line": 12},
}


def note(character, text):
    visible["note"] = text
    return {"ok": True, "text": text}


client.note.side_effect = note
client.glyph.return_value = [[[0, 0], [1, 1]]]
tools.service._client = client
tools.service._glyph_ids.by_word["test-character"] = "qrag"
tools.service._glyph_ids.by_id["qrag"] = "test-character"
run()
