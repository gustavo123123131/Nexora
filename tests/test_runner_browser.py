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
                        screenshot = manager.run('frame', first)
                        self.assertTrue(screenshot.startswith(b'\\xff\\xd8') or
                                        screenshot.startswith(bytes([0xff, 0xd8])))
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


if __name__ == '__main__':
    unittest.main()
