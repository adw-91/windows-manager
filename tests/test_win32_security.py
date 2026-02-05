"""Tests for win32 security helpers."""
import os
import unittest
from src.utils.win32.security import (
    get_current_user_sid,
    is_user_admin,
    get_current_username,
    get_current_domain,
)


class TestSecurity(unittest.TestCase):
    def test_get_current_user_sid(self):
        sid = get_current_user_sid()
        self.assertIsNotNone(sid)
        # SIDs start with S-1-5-
        self.assertTrue(sid.startswith("S-1-5-"), f"SID format unexpected: {sid}")

    def test_is_user_admin(self):
        result = is_user_admin()
        self.assertIsInstance(result, bool)

    def test_get_current_username(self):
        name = get_current_username()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)
        # Should match environment variable
        self.assertEqual(name, os.environ.get("USERNAME", name))

    def test_get_current_domain(self):
        domain = get_current_domain()
        self.assertIsInstance(domain, str)
        self.assertGreater(len(domain), 0)


if __name__ == "__main__":
    unittest.main()
