"""Tests for IP filter"""

import unittest

from ser2tcp.ip_filter import IpFilter, create_filter


class TestIpFilter(unittest.TestCase):
    """Test IpFilter class"""

    def test_no_rules_allows_all(self):
        """No rules should allow all IPs"""
        flt = IpFilter()
        self.assertTrue(flt.is_allowed('192.168.1.1'))
        self.assertTrue(flt.is_allowed('10.0.0.1'))
        self.assertTrue(flt.is_allowed('8.8.8.8'))

    def test_allow_single_ip(self):
        """Allow list with single IP"""
        flt = IpFilter(allow=['192.168.1.100'])
        self.assertTrue(flt.is_allowed('192.168.1.100'))
        self.assertFalse(flt.is_allowed('192.168.1.101'))
        self.assertFalse(flt.is_allowed('10.0.0.1'))

    def test_allow_cidr(self):
        """Allow list with CIDR notation"""
        flt = IpFilter(allow=['192.168.1.0/24'])
        self.assertTrue(flt.is_allowed('192.168.1.1'))
        self.assertTrue(flt.is_allowed('192.168.1.254'))
        self.assertFalse(flt.is_allowed('192.168.2.1'))
        self.assertFalse(flt.is_allowed('10.0.0.1'))

    def test_allow_multiple(self):
        """Allow list with multiple entries"""
        flt = IpFilter(allow=['192.168.1.0/24', '10.0.0.5'])
        self.assertTrue(flt.is_allowed('192.168.1.50'))
        self.assertTrue(flt.is_allowed('10.0.0.5'))
        self.assertFalse(flt.is_allowed('10.0.0.6'))

    def test_deny_single_ip(self):
        """Deny list with single IP"""
        flt = IpFilter(deny=['192.168.1.100'])
        self.assertFalse(flt.is_allowed('192.168.1.100'))
        self.assertTrue(flt.is_allowed('192.168.1.101'))
        self.assertTrue(flt.is_allowed('10.0.0.1'))

    def test_deny_cidr(self):
        """Deny list with CIDR notation"""
        flt = IpFilter(deny=['10.0.0.0/8'])
        self.assertFalse(flt.is_allowed('10.0.0.1'))
        self.assertFalse(flt.is_allowed('10.255.255.255'))
        self.assertTrue(flt.is_allowed('192.168.1.1'))

    def test_deny_takes_precedence(self):
        """Deny should take precedence over allow"""
        flt = IpFilter(
            allow=['192.168.1.0/24'],
            deny=['192.168.1.100'])
        self.assertTrue(flt.is_allowed('192.168.1.1'))
        self.assertTrue(flt.is_allowed('192.168.1.99'))
        self.assertFalse(flt.is_allowed('192.168.1.100'))
        self.assertTrue(flt.is_allowed('192.168.1.101'))

    def test_deny_without_allow(self):
        """Deny only - all allowed except denied"""
        flt = IpFilter(deny=['10.0.0.0/8'])
        self.assertTrue(flt.is_allowed('192.168.1.1'))
        self.assertTrue(flt.is_allowed('8.8.8.8'))
        self.assertFalse(flt.is_allowed('10.1.2.3'))

    def test_invalid_ip(self):
        """Invalid IP address should be denied"""
        flt = IpFilter(allow=['192.168.1.0/24'])
        self.assertFalse(flt.is_allowed('invalid'))
        self.assertFalse(flt.is_allowed(''))
        self.assertFalse(flt.is_allowed('256.1.1.1'))

    def test_ipv6(self):
        """IPv6 addresses"""
        flt = IpFilter(allow=['::1', 'fe80::/10'])
        self.assertTrue(flt.is_allowed('::1'))
        self.assertTrue(flt.is_allowed('fe80::1'))
        self.assertFalse(flt.is_allowed('2001:db8::1'))

    def test_is_enabled(self):
        """is_enabled property"""
        self.assertFalse(IpFilter().is_enabled)
        self.assertTrue(IpFilter(allow=['1.2.3.4']).is_enabled)
        self.assertTrue(IpFilter(deny=['1.2.3.4']).is_enabled)

    def test_invalid_network_in_config(self):
        """Invalid network in config should be skipped with warning"""
        flt = IpFilter(allow=['192.168.1.0/24', 'invalid', '10.0.0.0/8'])
        self.assertTrue(flt.is_allowed('192.168.1.1'))
        self.assertTrue(flt.is_allowed('10.0.0.1'))
        # Only 2 valid networks should be parsed
        self.assertEqual(len(flt._allow), 2)


class TestCreateFilter(unittest.TestCase):
    """Test create_filter function"""

    def test_no_config(self):
        """No allow/deny in config returns None"""
        self.assertIsNone(create_filter({}))
        self.assertIsNone(create_filter({'port': 8080}))

    def test_with_allow(self):
        """Config with allow list"""
        flt = create_filter({'allow': ['192.168.1.0/24']})
        self.assertIsNotNone(flt)
        self.assertTrue(flt.is_allowed('192.168.1.1'))

    def test_with_deny(self):
        """Config with deny list"""
        flt = create_filter({'deny': ['10.0.0.0/8']})
        self.assertIsNotNone(flt)
        self.assertFalse(flt.is_allowed('10.1.2.3'))

    def test_with_both(self):
        """Config with both allow and deny"""
        flt = create_filter({
            'allow': ['192.168.0.0/16'],
            'deny': ['192.168.1.100']
        })
        self.assertIsNotNone(flt)
        self.assertTrue(flt.is_allowed('192.168.2.1'))
        self.assertFalse(flt.is_allowed('192.168.1.100'))


if __name__ == '__main__':
    unittest.main()
