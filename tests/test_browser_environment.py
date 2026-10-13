"""Reproducible browser-environment audit without contacting Fingerprint or the internet.

It compares the former explicit pt-BR/Sao_Paulo options with the current
host-derived defaults on the *same* Playwright build. It cannot reproduce the
user's Fingerprint.com risk score or inspect their Windows environment.
"""
import json
import platform
import re
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright
from runner.worker import chromium_launch_options


EVAL = """async () => {
  const hints = navigator.userAgentData;
  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    uaClientHintsPlatform: hints ? hints.platform : null,
    uaClientHintsMobile: hints ? hints.mobile : null,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
    screenWidth: screen.width,
    screenHeight: screen.height,
    pixelRatio: devicePixelRatio,
    touchPoints: navigator.maxTouchPoints,
    language: navigator.language,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    webdriver: navigator.webdriver,
    webglRenderer: (() => {
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('webgl');
      return context ? context.getParameter(context.RENDERER) : null;
    })()
  };
}"""


def collect(pw, options):
    with tempfile.TemporaryDirectory(prefix='nexora-browser-audit-') as directory:
        options = dict(options, headless=True)
        options['args'] = [item for item in options['args']
                           if not item.startswith('--window-size=')]
        context = pw.chromium.launch_persistent_context(str(Path(directory)), **options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            return page.evaluate(EVAL)
        finally:
            context.close()


class BrowserEnvironmentAudit(unittest.TestCase):
    def test_before_after_browser_properties(self):
        with sync_playwright() as pw:
            current = chromium_launch_options(pw)
            before = dict(current, locale='pt-BR',
                          timezone_id='America/Sao_Paulo')
            old = collect(pw, before)
            after = collect(pw, current)
            comparison = {
                'platformOfRunner': platform.system(),
                'oldHardcodedOptions': {'locale': 'pt-BR', 'timezone_id': 'America/Sao_Paulo'},
                'newOptions': {'locale': 'host default', 'timezone_id': 'host default'},
                'before': old,
                'after': after,
            }
            # This output intentionally excludes IPs, passwords, cookies,
            # browsing history and private-account information.
            print('NEXORA_BROWSER_BEFORE_AFTER=' +
                  json.dumps(comparison, sort_keys=True, ensure_ascii=False), flush=True)

            for key in ('userAgent', 'platform', 'uaClientHintsPlatform',
                        'uaClientHintsMobile', 'viewportWidth', 'viewportHeight',
                        'screenWidth', 'screenHeight', 'pixelRatio',
                        'touchPoints', 'webdriver', 'webglRenderer'):
                self.assertEqual(old[key], after[key],
                                 'Localization changes must not affect ' + key)
            self.assertIn('Android', after['userAgent'])
            self.assertGreater(after['touchPoints'], 0)
            self.assertTrue(after['viewportWidth'] > 0)
            self.assertEqual(old['language'], 'pt-BR')
            self.assertEqual(old['timeZone'], 'America/Sao_Paulo')
            self.assertNotIn('locale', current)
            self.assertNotIn('timezone_id', current)
            # Playwright remains automation. Explicitly assert no stealth
            # workarounds were introduced in the production configuration.
            self.assertIs(after['webdriver'], True)


if __name__ == '__main__':
    unittest.main()
