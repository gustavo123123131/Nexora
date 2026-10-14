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
        valid_keys = ('user_agent', 'viewport', 'screen', 'device_scale_factor',
                      'is_mobile', 'has_touch', 'default_browser_type')
        descriptors = {
            name: {key: playwright.devices[name][key] for key in valid_keys
                   if key in playwright.devices[name]}
            for name in names
        }
    if 'Pixel 7' not in names or len(names) < 20:
        raise RuntimeError('A lista de dispositivos foi alterada inesperadamente.')
    current_version = version('playwright')
    manifest = {
        'schema_version': 1,
        'source': ('microsoft/playwright v' + current_version +
                   ' packages/playwright-core/src/server/deviceDescriptorsSource.json'),
        'default_device': 'Pixel 7',
        'devices': names,
    }
    snapshots = {
        'schema_version': 1,
        'source': ('microsoft/playwright v' + current_version +
                   ' deviceDescriptorsSource.json'),
        'playwright_version': current_version,
        'devices': descriptors,
    }
    for filename in ('runner/device_catalog.json', 'public/device_catalog.json'):
        (ROOT / filename).write_text(json.dumps(manifest, indent=2, ensure_ascii=False)
                                     + '\\n', encoding='utf-8')
    (ROOT / 'runner/device_descriptors.json').write_text(
        json.dumps(snapshots, indent=2, ensure_ascii=False) + '\\n', encoding='utf-8')
    print('Presets Chromium Android:', len(names))
    print('Atualizados: catálogo do painel, executor e descritores versionados')

if __name__ == '__main__':
    main()
