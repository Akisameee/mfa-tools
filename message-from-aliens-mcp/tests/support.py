"""Isolated service state and a native-client stand-in for public contract tests."""

import unittest
from unittest.mock import Mock

from aliens_mcp import tools

service = tools.service


def mock_game(**kwargs):
    client = Mock(**kwargs)
    client.vocabulary.return_value = ["test-character"]
    client.snapshot.return_value = {"cells": []}
    return client


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        service.reset_session()
        # A controlled connection-local index for tool schema/receipt tests.
        service._glyph_ids.by_word["test-character"] = "qrag"
        service._glyph_ids.by_id["qrag"] = "test-character"
        self.addCleanup(service.reset_session)
