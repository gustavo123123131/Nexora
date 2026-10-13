"""Offline, reproducible Playwright diagnostics: no user IP, accounts or score.

Old = the same device preset with the formerly hardcoded pt-BR/Sao_Paulo.
New = identical preset without those overrides (OS-derived defaults).
Both contexts visit a local loopback fixture so JS, viewport meta and HTTP
User-Agent / Client Hints can be compared objectively.
"""
import json
import platform
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright
from runner.worker import chromium_launch_options, host_browser_locale, DEVICE_MODELS


JS = """async () => {
  const hints = navigator.userAgentData;
  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    uaClientHintsPlatform: hints ? hints.platform : null,
    uaClientHintsMobile: hints ? hints.mobile : null,
    viewportWidth: innerWidth,
    viewportHeight: innerHeight,
    screenWidth: screen.width,
    screenHeight: screen.height,
    pixelRatio: devicePixelRatio,
    touchPoints: navigator.maxTouchPoints,
    language: navigator.language,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    webdriver: navigator.webdriver,
    webglRenderer: (() => {
      const gl = document.createElement('canvas').getContext('webgl');
      return gl ? gl.getParameter(gl.RENDERER) : null;
    })()
  };
}"""


class PageFixture(BaseHTTPRequestHandler):
    header_samples = []

    def do_GET(self):
        if self.path == '/':
            PageFixture.header_samples.append({
                key: self.headers.get(key) for key in
                ('User-Agent', 'Accept-Language',
                 'Sec-CH-UA-Platform', 'Sec-CH-UA-Mobile')
            })
        body = (b'<!doctype html><html><head><meta name="viewport" '
                b'content="width=device-width, initial-scale=1"></head>'
                b'<body><p>Nexora test fixture</p></body></html>')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def collect(playwright, options, url):
    with tempfile.TemporaryDirectory(prefix='nexora-audit-') as directory:
        options = dict(options, headless=True)
        options['args'] = [item for item in options['args']
                           if not item.startswith('--window-size=')]
        context = playwright.chromium.launch_persistent_context(
            str(Path(directory)), **options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until='domcontentloaded')
            properties = page.evaluate(JS)
            self_report = dict(properties)
            return self_report
        finally:
            context.close()


class BrowserEnvironmentAudit(unittest.TestCase):
    def test_every_offered_device_preset_is_real_and_chromium_compatible(self):
        with sync_playwright() as playwright:
            for name in DEVICE_MODELS:
                with self.subTest(device=name):
                    self.assertIn(name, playwright.devices)
                    options = chromium_launch_options(playwright, name)
                    self.assertTrue(options.get('is_mobile'))
                    self.assertTrue(options.get('has_touch'))
                    self.assertIn('Android', options['user_agent'])
                    self.assertGreater(options['viewport']['width'], 0)
                    self.assertGreater(options['viewport']['height'], 0)

    def test_before_after_browser_properties(self):
        PageFixture.header_samples.clear()
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), PageFixture)
        threading.Thread(target=fixture.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:%d/' % fixture.server_port
        try:
            with sync_playwright() as playwright:
                after_options = chromium_launch_options(playwright)
                before_options = dict(after_options, locale='pt-BR',
                                      timezone_id='America/Sao_Paulo')
                before = collect(playwright, before_options, url)
                after = collect(playwright, after_options, url)
                self.assertEqual(len(PageFixture.header_samples), 2)
                comparison = {
                    'testPlatform': platform.system(),
                    'oldOptions': {'locale': 'pt-BR', 'timezone_id': 'America/Sao_Paulo'},
                    'newOptions': {'locale': 'detected from OS', 'timezone_id': 'host default'},
                    'before': {**before, 'httpHeaders': PageFixture.header_samples[0]},
                    'after': {**after, 'httpHeaders': PageFixture.header_samples[1]},
                }
                print('NEXORA_BROWSER_BEFORE_AFTER=' +
                      json.dumps(comparison, sort_keys=True, ensure_ascii=False),
                      flush=True)

                for name in ('userAgent', 'platform', 'uaClientHintsPlatform',
                             'uaClientHintsMobile', 'viewportWidth', 'viewportHeight',
                             'screenWidth', 'screenHeight', 'pixelRatio',
                             'touchPoints', 'webdriver', 'webglRenderer'):
                    self.assertEqual(before[name], after[name], name)
                preset = playwright.devices['Pixel 7']
                self.assertEqual(after['viewportWidth'], preset['viewport']['width'])
                self.assertEqual(after['viewportHeight'], preset['viewport']['height'])
                self.assertEqual(after['pixelRatio'], preset['device_scale_factor'])
                self.assertIn('Android', after['userAgent'])
                self.assertGreater(after['touchPoints'], 0)
                self.assertEqual(before['language'], 'pt-BR')
                self.assertEqual(before['timeZone'], 'America/Sao_Paulo')
                self.assertEqual(after_options.get('locale'), host_browser_locale())
                self.assertNotIn('timezone_id', after_options)
                self.assertIs(after['webdriver'], True)
                self.assertEqual(PageFixture.header_samples[0]['User-Agent'],
                                 PageFixture.header_samples[1]['User-Agent'])
                self.assertEqual(after['language'], after_options['locale'])
                self.assertEqual(PageFixture.header_samples[1]['Accept-Language'],
                                 after_options['locale'])
        finally:
            fixture.shutdown()
            fixture.server_close()


if __name__ == '__main__':
    unittest.main()
