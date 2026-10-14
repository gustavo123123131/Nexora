"""Native manual Chrome profile tests, without opening external websites."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from storage import Store
from manual_browser_manager import ManualChromeManager, find_chrome
from server import LocalServer


class ManualChromeTests(unittest.TestCase):
    def test_profiles_are_isolated_and_no_automation_flags_are_used(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            site = store.create_site('Teste', 'https://example.org/')
            first = store.create_profile('Primeiro', site['id'])
            second = store.create_profile('Segundo', site['id'])
            browser = Path(folder) / 'chrome.exe'
            browser.write_bytes(b'fake executable (not run)')
            manager = ManualChromeManager(store, executable_path=str(browser))
            processes = []
            commands = []

            def fake_popen(args, **options):
                self.assertFalse(options['shell'])
                self.assertEqual(args[0], str(browser))
                self.assertIn('--new-window', args)
                self.assertFalse(any('remote-debugging' in arg or
                                     'automation' in arg for arg in args))
                commands.append(args)
                process = MagicMock()
                process.poll.return_value = None
                processes.append(process)
                return process

            with patch('manual_browser_manager.subprocess.Popen', side_effect=fake_popen):
                manager.start(first['id'])
                manager.start(second['id'])
                self.assertTrue(manager.is_running(first['id']))
                self.assertTrue(manager.is_running(second['id']))
                self.assertNotEqual(commands[0][1], commands[1][1])
                self.assertIn('chrome-manual', commands[0][1])
                self.assertIn('chrome-manual', commands[1][1])
                self.assertEqual(len(commands), 2)
                self.assertTrue(manager.start(first['id'])['already_open'])
                self.assertEqual(len(commands), 2)
                report = manager.inspect(first['id'])
                self.assertIsNone(report['observed'])
                self.assertFalse(report['configured']['mobile_preset_applied'])
                with self.assertRaisesRegex(ValueError, 'feche a janela'):
                    manager.stop(first['id'])
                processes[0].poll.return_value = 0
                self.assertFalse(manager.is_running(first['id']))
                manager.stop_all()
                self.assertTrue(manager.is_running(second['id']))
                processes[1].poll.return_value = 0
                self.assertFalse(manager.is_running(second['id']))

    def test_localhost_backend_selection_and_default(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict('os.environ', {'MULTILOGIN_BROWSER_MODE': 'chrome-manual'}):
                srv = LocalServer(port=0, data_dir=folder)
                try:
                    self.assertIsInstance(srv.manager, ManualChromeManager)
                finally:
                    srv.server_close()
            with patch.dict('os.environ', {'MULTILOGIN_BROWSER_MODE': 'playwright'}):
                srv = LocalServer(port=0, data_dir=folder)
                try:
                    self.assertNotIsInstance(srv.manager, ManualChromeManager)
                finally:
                    srv.server_close()

    def test_explicit_chrome_path_is_checked(self):
        with patch.dict('os.environ', {'MULTILOGIN_CHROME_PATH': '/not/a/real/chrome'}):
            with self.assertRaises(FileNotFoundError):
                find_chrome()


if __name__ == '__main__':
    unittest.main()
