"""Unit tests for the Addy.io/Gmail metadata delivery diagnostic."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "addy_gmail_test.py"
spec = importlib.util.spec_from_file_location("addy_gmail_test", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HeaderTests(unittest.TestCase):
    def test_forwarded_recipient(self):
        headers = [
            {"name": "Delivered-To", "value": "my-gmail@gmail.com"},
            {"name": "To", "value": "Test Alias <alias@anonaddy.me>"},
        ]
        self.assertTrue(mod.matches_alias(headers, "ALIAS@anonaddy.me"))

    def test_ignores_subject_and_sender(self):
        headers = [
            {"name": "Subject", "value": "alias@anonaddy.me"},
            {"name": "From", "value": "alias@anonaddy.me"},
        ]
        self.assertFalse(mod.matches_alias(headers, "alias@anonaddy.me"))

    def test_cc_multiple(self):
        headers = [{"name": "Cc", "value": "One <one@example.org>, Two <two@example.org>"}]
        self.assertTrue(mod.matches_alias(headers, "two@example.org"))
        self.assertFalse(mod.matches_alias(headers, "three@example.org"))

    def test_create_alias_payload(self):
        result = {"data": {"id": "abc", "email": "x@anonaddy.me"}}
        with patch.object(mod, "addy_request", return_value=result) as fake:
            self.assertEqual(mod.create_alias("anonaddy.me"), ("abc", "x@anonaddy.me"))
            fake.assert_called_once_with("POST", "/aliases", data={
                "domain": "anonaddy.me",
                "format": "uuid",
                "description": "Personal Addy to Gmail delivery test",
            })


if __name__ == "__main__":
    unittest.main()
