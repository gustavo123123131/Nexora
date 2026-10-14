"""Compatibility checks for the uploaded mobile UA list; no spoofing."""
import json
import tempfile
import unittest
from pathlib import Path

from mobile_ua_catalog import audit_mobile_user_agents

PIXEL_7_UA = ('Mozilla/5.0 (Linux; Android 14; Pixel 7) '
              'AppleWebKit/537.36 (KHTML, like Gecko) '
              'Chrome/143.0.7499.4 Mobile Safari/537.36')


class MobileUserAgentCatalogTests(unittest.TestCase):
    def test_uploaded_catalog_is_classified_without_touching_browser(self):
        report = audit_mobile_user_agents(PIXEL_7_UA, PIXEL_7_UA)
        self.assertTrue(report['available'])
        self.assertFalse(report['applied_to_browser'])
        self.assertEqual(report['total_entries'], 180)
        self.assertEqual(report['unique_entries'], 142)
        self.assertEqual(report['duplicates'], 38)
        self.assertEqual(report['android_entries'], 120)
        self.assertEqual(report['iphone_safari_entries'], 60)
        self.assertEqual(report['configured_chrome_version'], '143.0.7499.4')
        self.assertEqual(report['same_chrome_build_entries'], 0)
        self.assertEqual(report['same_chrome_major_entries'], 22)
        self.assertFalse(report['configured_ua_present_in_list'])
        self.assertFalse(report['observed_ua_present_in_list'])
        self.assertTrue(report['observed_equals_configured'])
        self.assertIn('140.0.7339.41', report['reference_chrome_versions'])

    def test_missing_catalog_is_never_applied(self):
        with tempfile.TemporaryDirectory() as folder:
            report = audit_mobile_user_agents(
                PIXEL_7_UA, path=Path(folder) / 'missing.json')
            self.assertFalse(report['available'])
            self.assertFalse(report['applied_to_browser'])

    def test_corrupt_or_unsupported_catalog_is_not_used(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / 'ua.json'
            for invalid in ('broken', '{}', '{"userAgents":"abc"}',
                            '{"userAgents":[123]}'):
                filename.write_text(invalid, encoding='utf-8')
                report = audit_mobile_user_agents(PIXEL_7_UA, path=filename)
                self.assertFalse(report['available'])
                self.assertFalse(report['applied_to_browser'])

    def test_synthetic_reference_does_not_change_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / 'ua.json'
            filename.write_text(json.dumps({'userAgents': [PIXEL_7_UA]}))
            report = audit_mobile_user_agents(PIXEL_7_UA, path=filename)
            self.assertTrue(report['configured_ua_present_in_list'])
            self.assertEqual(report['same_chrome_build_entries'], 1)
            self.assertFalse(report['applied_to_browser'])


if __name__ == '__main__':
    unittest.main()
