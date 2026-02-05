"""Tests for win32 GPO enumeration."""
import unittest
from src.utils.win32.gpo import get_applied_gpos


class TestGpo(unittest.TestCase):
    def test_get_machine_gpos_returns_list(self):
        """Machine GPO list should always be a list (may be empty on non-domain machines)."""
        result = get_applied_gpos(machine=True)
        self.assertIsInstance(result, list)

    def test_get_user_gpos_returns_list(self):
        result = get_applied_gpos(machine=False)
        self.assertIsInstance(result, list)

    def test_gpo_names_are_strings(self):
        for gpo in get_applied_gpos(machine=True):
            self.assertIsInstance(gpo, str)
            self.assertGreater(len(gpo), 0)


if __name__ == "__main__":
    unittest.main()
