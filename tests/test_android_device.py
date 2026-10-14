"""Android device backend: isolated manual sessions, no real phone required in CI."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from android_device_manager import AndroidDeviceManager
from server import LocalServer
from storage import Store


class AndroidDeviceTests(unittest.TestCase):
    def setup_profiles(self, folder):
        store = Store(folder)
        site = store.create_site('Site', 'https://example.org/path?x=1&y=2')
        a = store.create_profile('Android um', site['id'])
        b = store.create_profile('Android dois', site['id'])
        return store, a, b

    def test_connected_devices_and_independent_phone_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            store, a, b = self.setup_profiles(folder)
            manager = AndroidDeviceManager(store)
            adb_output = subprocess.CompletedProcess(
                ['adb', 'devices'], 0,
                'List of devices attached\nUSB_001\tdevice\nUSB_002\tdevice\nUSB_003\tunauthorized\n', '')
            opened = []
            processes = []

            def run(args, **kwargs):
                if args[1:] == ['devices']:
                    return adb_output
                self.assertIn('-s', args)
                self.assertIn('shell', args)
                self.assertIn('am start -a android.intent.action.VIEW -d ', args[-1])
                self.assertIn("'https://example.org/path?x=1&y=2'", args[-1])
                opened.append(args)
                return subprocess.CompletedProcess(args, 0, '', '')

            def popen(args, **kwargs):
                self.assertTrue(args[1].startswith('--serial='))
                self.assertFalse(kwargs['shell'])
                self.assertFalse(any('webdriver' in part or 'debug' in part for part in args))
                process = MagicMock()
                process.poll.return_value = None
                processes.append(process)
                return process

            with (patch('android_device_manager.executable', side_effect=lambda name, env: name),
                  patch('android_device_manager.subprocess.run', side_effect=run),
                  patch('android_device_manager.subprocess.Popen', side_effect=popen)):
                devices = manager.list_devices()
                self.assertEqual(len(devices), 3)
                self.assertFalse(devices[2]['available'])
                self.assertRaisesRegex(ValueError, 'Escolha', manager.start, a['id'])
                manager.start(a['id'], 'USB_001')
                with self.assertRaisesRegex(ValueError, 'já está vinculado'):
                    manager.start(b['id'], 'USB_001')
                manager.start(b['id'], 'USB_002')
                self.assertEqual(len(opened), 2)
                self.assertEqual(len(processes), 2)
                self.assertTrue(manager.is_running(a['id']))
                self.assertTrue(manager.is_running(b['id']))
                report = manager.inspect(a['id'])
                self.assertEqual(report['mode'], 'android-real')
                self.assertIsNone(report['observed'])
                self.assertFalse(report['configured']['playwright_fingerprint_applied'])
                self.assertEqual(report['configured']['device_serial'], 'USB_001')
                manager.stop(a['id'])
                processes[0].terminate.assert_called_once()
                self.assertFalse(manager.is_running(a['id']))
                manager.stop_all()
                processes[1].terminate.assert_called_once()
                self.assertFalse(manager.is_running(b['id']))

    def test_single_device_auto_selected_and_disconnected(self):
        with tempfile.TemporaryDirectory() as folder:
            store, a, _ = self.setup_profiles(folder)
            manager = AndroidDeviceManager(store)
            with patch.object(manager, 'list_devices', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'Nenhum Android'):
                    manager.start(a['id'])
            with patch.object(manager, 'list_devices', return_value=[{
                'serial': 'USB_001', 'available': True, 'state': 'device'}]):
                with patch('android_device_manager.executable', side_effect=lambda n, e: n):
                    with patch('android_device_manager.subprocess.run') as run:
                        with patch('android_device_manager.subprocess.Popen') as popen:
                            process = popen.return_value
                            process.poll.return_value = None
                            result = manager.start(a['id'])
                            self.assertEqual(result['serial'], 'USB_001')
                            process.poll.return_value = 1
                            self.assertFalse(manager.is_running(a['id']))

    def test_backend_is_opt_in_and_default_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict('os.environ', {'MULTILOGIN_BROWSER_MODE': 'android-real'}):
                server = LocalServer(port=0, data_dir=folder)
                try:
                    self.assertIsInstance(server.manager, AndroidDeviceManager)
                finally:
                    server.server_close()
            with patch.dict('os.environ', {'MULTILOGIN_BROWSER_MODE': 'playwright'}):
                server = LocalServer(port=0, data_dir=folder)
                try:
                    self.assertNotIsInstance(server.manager, AndroidDeviceManager)
                finally:
                    server.server_close()


if __name__ == '__main__':
    unittest.main()
