"""
Tests for config.log_formatter.JSONFormatter — guarantees the production
log line shape (one JSON object per record, ISO-8601 ts, exc_info flattened).
"""

import json
import logging
from datetime import datetime

from django.test import TestCase

from config.log_formatter import JSONFormatter


def _make_record(**overrides):
    base = {
        "name": "apps.test",
        "level": logging.INFO,
        "pathname": __file__,
        "lineno": 1,
        "msg": "hello %s",
        "args": ("world",),
        "exc_info": None,
    }
    base.update(overrides)
    return logging.LogRecord(**base)


class JSONFormatterTests(TestCase):
    def setUp(self):
        self.formatter = JSONFormatter()

    def test_basic_record_emits_json(self):
        out = self.formatter.format(_make_record())
        payload = json.loads(out)
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "apps.test")
        self.assertEqual(payload["msg"], "hello world")
        # ts must be ISO-8601 parseable.
        datetime.fromisoformat(payload["ts"])

    def test_extra_fields_are_included(self):
        record = _make_record()
        record.user_id = 42
        record.path = "/api/x/"
        out = self.formatter.format(record)
        payload = json.loads(out)
        self.assertEqual(payload["user_id"], 42)
        self.assertEqual(payload["path"], "/api/x/")

    def test_reserved_fields_are_not_duplicated(self):
        record = _make_record()
        out = self.formatter.format(record)
        payload = json.loads(out)
        # internal LogRecord attributes must not leak into the JSON envelope.
        self.assertNotIn("args", payload)
        self.assertNotIn("levelno", payload)
        self.assertNotIn("pathname", payload)

    def test_exc_info_is_flattened(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = _make_record(exc_info=sys.exc_info())
        out = self.formatter.format(record)
        payload = json.loads(out)
        self.assertIn("exc_info", payload)
        self.assertIn("ValueError", payload["exc_info"])
        self.assertIn("boom", payload["exc_info"])
