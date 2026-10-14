"""Regenerate browser and Windows runner catalogs from installed Playwright.

Usage after upgrading pinned Playwright in BOTH runner requirements files:
  python scripts/update_device_catalog.py

This script does not fetch anything from the internet or invent device specs.
Only Android, touch-enabled, Chromium-compatible Playwright presets are used.
"""
import json
import sys
from importlib.metadata import version
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

def main():
    with sync_playwright() as playwright:
        names = sorted(name for name, item in playwright.devices.items()
                       if item.get('default_browser_type') == 'chromium'
                       and item.get('is_mobile') and item.get('has_touch')
                       and 'Android' in item.get('user_agent', '')
                       and 'Windows Phone' not in item.get('user_agent', ''))
    if 'Pixel 7' not in names or len(names) < 20:
        raise RuntimeError('A lista de dispositivos foi alterada inesperadamente.')
    manifest = {
        'schema_version': 1,
        'source': ('microsoft/playwright v' + version('playwright') +
                   ' packages/playwright-core/src/server/deviceDescriptorsSource.json'),
        'default_device': 'Pixel 7',
        'devices': names,
    }
    contents = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    for filename in ('runner/device_catalog.json', 'public/device_catalog.json'):
        (ROOT / filename).write_text(contents, encoding='utf-8')
    print('Presets Chromium Android:', len(names))
    print('Atualizados: runner/device_catalog.json, public/device_catalog.json')

if __name__ == '__main__':
    main()
