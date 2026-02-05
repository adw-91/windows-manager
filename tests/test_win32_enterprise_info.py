"""Tests for EnterpriseInfo using native APIs."""
import unittest
from src.services.enterprise_info import EnterpriseInfo


class TestEnterpriseInfo(unittest.TestCase):
    def test_get_domain_info(self):
        info = EnterpriseInfo()
        domain = info.get_domain_info()
        self.assertIn("domain_name", domain)
        self.assertIn("is_domain_joined", domain)
        self.assertIsInstance(domain["is_domain_joined"], bool)

    def test_get_computer_info(self):
        info = EnterpriseInfo()
        comp = info.get_computer_info()
        self.assertIn("computer_name", comp)
        self.assertGreater(len(comp["computer_name"]), 0)

    def test_get_current_user(self):
        info = EnterpriseInfo()
        user = info.get_current_user()
        self.assertIn("username", user)
        self.assertIn("sid", user)
        self.assertIn("is_admin", user)
        self.assertNotEqual(user["username"], "Unknown")
        # SID should start with S-
        self.assertTrue(user["sid"].startswith("S-"), f"Unexpected SID: {user['sid']}")

    def test_get_network_info(self):
        info = EnterpriseInfo()
        net = info.get_network_info()
        self.assertIn("primary_ip", net)

    def test_get_azure_ad_info(self):
        info = EnterpriseInfo()
        aad = info.get_azure_ad_info()
        self.assertIn("is_azure_ad_joined", aad)
        self.assertIsInstance(aad["is_azure_ad_joined"], bool)

    def test_get_group_policy_info(self):
        info = EnterpriseInfo()
        gp = info.get_group_policy_info()
        self.assertIn("gpos_applied", gp)
        self.assertIn("computer_policies", gp)
        self.assertIn("user_policies", gp)


if __name__ == "__main__":
    unittest.main()
