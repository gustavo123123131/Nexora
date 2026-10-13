"""Smoke test using actual Chromium contexts, without uploading any credentials."""
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from runner import worker as runner_module


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        body = (b'<!doctype html><html><head><meta name="viewport" '
                b'content="width=device-width,initial-scale=1"></head>'
                b'<body><input placeholder="Login"></body></html>')
        self.send_response(200)
        if self.path == '/first':
            self.send_header('Set-Cookie', 'first_profile=one; Path=/')
        elif self.path == '/second':
            self.send_header('Set-Cookie', 'second_profile=two; Path=/')
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ChromiumRunnerTests(unittest.TestCase):
    def test_profile_isolation_persistence_and_screenshot(self):
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        threading.Thread(target=fixture.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % fixture.server_port
        first, second = 'a' * 32, 'b' * 32
        try:
            with tempfile.TemporaryDirectory() as home:
                with patch.object(runner_module, 'STORE', Path(home)):
                    manager = runner_module.BrowserWorker()
                    try:
                        # Bypass public URL validator ONLY inside this local
                        # test so we can use a private fixture with no internet.
                        self.assertTrue(manager.run('start', first, base + '/first')['running'])
                        self.assertTrue(manager.run('start', second, base + '/second')['running'])
                        c1 = manager.run('_cookie_names_for_test', first)
                        c2 = manager.run('_cookie_names_for_test', second)
                        self.assertIn('first_profile', c1)
                        self.assertNotIn('first_profile', c2)
                        self.assertIn('second_profile', c2)
                        self.assertNotIn('second_profile', c1)
                        if runner_module.DESKTOP_MODE:
                            # Visible Chromium windows are used directly:
                            # validate a live interactive page, not screenshot streaming.
                            page = manager.run('_page_url_for_test', first)
                            self.assertEqual(page['url'], base + '/first')
                            self.assertEqual(page['input_count'], 1)
                        else:
                            screenshot = manager.run('frame', first)
                            self.assertTrue(screenshot.startswith(bytes([0xff, 0xd8])))
                            self.assertGreater(len(screenshot), 1000)
                        self.assertTrue(manager.run('stop', first)['running'] is False)
                        self.assertTrue(manager.run('start', first, base + '/plain')['running'])
                        self.assertIn('first_profile', manager.run('_cookie_names_for_test', first))
                    finally:
                        manager.run('stop', first)
                        manager.run('stop', second)
        finally:
            fixture.shutdown()
            fixture.server_close()




class DesktopChromiumConfigurationTests(unittest.TestCase):
    """The Windows executor must never start a hidden Chromium process."""

    def test_native_windows_mode_preserves_pixel7_emulation(self):
        from types import SimpleNamespace
        fake = SimpleNamespace(devices={'Pixel 7': {
            'user_agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36',
            'viewport': {'width': 412, 'height': 915},
            'device_scale_factor': 2.625,
            'is_mobile': True,
            'has_touch': True,
            'default_browser_type': 'chromium'
        }})
        with patch.object(runner_module, 'DESKTOP_MODE', True):
            config = runner_module.chromium_launch_options(fake)
            self.assertIs(config['headless'], False)
            self.assertTrue(config['is_mobile'])
            self.assertTrue(config['has_touch'])
            self.assertEqual(config['viewport'], {'width': 412, 'height': 915})
            self.assertIn('Pixel 7', config['user_agent'])
            self.assertTrue(config['accept_downloads'])
            self.assertNotIn('locale', config)
            self.assertNotIn('timezone_id', config)
            # This application does not configure a residential proxy;
            # IP reputation belongs to the operating system/network.
            self.assertNotIn('proxy', config)
            self.assertFalse(any('--proxy-server' in flag
                                 for flag in config['args']))
            self.assertTrue(any(flag.startswith('--window-size=')
                                for flag in config['args']))
        with patch.object(runner_module, 'DESKTOP_MODE', False):
            config = runner_module.chromium_launch_options(fake)
            self.assertIs(config['headless'], True)


class TunnelCorsTests(unittest.TestCase):
    """Browser requests must be CORS-scoped and require the executor key."""
    def test_via_vercel_origin_only_and_bearer(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {'NEXORA_RUNNER_KEY': 'A' * 48}):
            client = runner_module.app.test_client()
            origin = 'https://nexora-ebon-eight.vercel.app'
            preflight = client.options('/v1/health', headers={
                'Origin': origin,
                'Access-Control-Request-Method': 'GET',
                'Access-Control-Request-Headers': 'authorization'})
            self.assertEqual(preflight.status_code, 204)
            self.assertEqual(preflight.headers['Access-Control-Allow-Origin'], origin)
            self.assertIn('Authorization', preflight.headers['Access-Control-Allow-Headers'])
            missing = client.get('/v1/health', headers={'Origin': origin})
            self.assertEqual(missing.status_code, 401)
            correct = client.get('/v1/health', headers={
                'Origin': origin, 'Authorization': 'Bearer ' + 'A' * 48})
            self.assertEqual(correct.status_code, 200)
            self.assertTrue(correct.json['browser'])
            blocked = client.get('/v1/health', headers={
                'Origin': 'https://evil.example',
                'Authorization': 'Bearer ' + 'A' * 48})
            self.assertEqual(blocked.status_code, 403)
            blocked_preflight = client.options('/v1/health', headers={'Origin': 'https://evil.example'})
            self.assertEqual(blocked_preflight.status_code, 403)

if __name__ == '__main__':
    unittest.main()
