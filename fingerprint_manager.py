"""Versioned, honest Playwright mobile emulation snapshots and browser inspection.

This does NOT fabricate hardware, intercept native APIs, or claim anti-fraud
invisibility. Snapshots represent a documented Playwright device emulation.
Real navigator and WebGL values are measured in a disposable local page.
"""
import json
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from mobile_ua_catalog import audit_mobile_user_agents

CATALOG = json.loads((Path(__file__).resolve().parent / 'runner' /
                      'device_descriptors.json').read_text(encoding='utf-8'))
SNAPSHOT_VERSION = 1


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class FingerprintManager:
    @staticmethod
    def generate(device, *, reason='created'):
        if not isinstance(device, str) or device not in CATALOG['devices']:
            raise ValueError('Preset de dispositivo não documentado.')
        return {
            'version': SNAPSHOT_VERSION,
            'engine': 'chromium',
            'playwright_version': CATALOG['playwright_version'],
            'preset': device,
            'descriptor': deepcopy(CATALOG['devices'][device]),
            'created_at': _utc_now(),
            'reason': reason,
            'scope': 'playwright-mobile-emulation-not-physical-hardware',
        }

    @staticmethod
    def validate(snapshot, device=None):
        if not isinstance(snapshot, dict):
            raise ValueError('Snapshot de navegador ausente.')
        name = snapshot.get('preset')
        if device is not None and name != device:
            raise ValueError('Preset salvo diverge da configuração do perfil.')
        if (name not in CATALOG['devices'] or
                snapshot.get('version') != SNAPSHOT_VERSION or
                snapshot.get('engine') != 'chromium' or
                snapshot.get('playwright_version') != CATALOG['playwright_version'] or
                snapshot.get('descriptor') != CATALOG['devices'][name]):
            raise ValueError('Snapshot incompatível: regenere a configuração com o navegador parado.')
        return snapshot

    @staticmethod
    def migrate_version(snapshot):
        try:
            FingerprintManager.validate(snapshot)
            return {'compatible': True, 'action_required': None}
        except ValueError:
            return {'compatible': False, 'action_required': 'explicit-regeneration'}

    @staticmethod
    def apply(playwright, snapshot):
        """Use actual Playwright devices, not injected JavaScript overrides."""
        FingerprintManager.validate(snapshot)
        if version('playwright') != CATALOG['playwright_version']:
            raise ValueError('Playwright atualizado: revise o preset antes de regenerar.')
        descriptor = playwright.devices.get(snapshot['preset'])
        # The Playwright Python bridge may normalize a device's optional
        # screen differently from the original JSON descriptor. Pin it to the
        # documented source for this snapshot, not to runtime defaults.
        differences = [key for key, value in snapshot['descriptor'].items()
                       if key != 'screen' and descriptor.get(key) != value]
        if differences:
            raise ValueError('Descritor em execução diferente do snapshot salvo: ' +
                             ', '.join(differences))
        options = {key: deepcopy(value) for key, value in descriptor.items()
                   if key != 'default_browser_type'}
        if 'screen' in snapshot['descriptor']:
            options['screen'] = deepcopy(snapshot['descriptor']['screen'])
        return options

    @staticmethod
    def inspect(context, snapshot, *, locale=None):
        """Read observable browser facts with NO network, cookies or passwords."""
        FingerprintManager.validate(snapshot)
        page = context.new_page()
        try:
            page.set_content('<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">')
            observed = page.evaluate("""() => {
              const n = navigator;
              let webgl = {vendor: null, renderer: null};
              try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                if (gl) {
                  webgl.vendor = gl.getParameter(gl.VENDOR);
                  webgl.renderer = gl.getParameter(gl.RENDERER);
                }
              } catch (_) {}
              const hints = n.userAgentData;
              return {
                userAgent: n.userAgent,
                platform: n.platform,
                webdriver: n.webdriver,
                userAgentData: hints ? {
                  platform: hints.platform,
                  mobile: hints.mobile,
                  brands: hints.brands
                } : null,
                language: n.language,
                languages: Array.from(n.languages || []),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                viewport: {width: innerWidth, height: innerHeight},
                screen: {width: screen.width, height: screen.height},
                devicePixelRatio: devicePixelRatio,
                maxTouchPoints: n.maxTouchPoints,
                hardwareConcurrency: n.hardwareConcurrency,
                deviceMemory: n.deviceMemory ?? null,
                webgl: webgl,
                audioSupport: !!window.AudioContext,
                videoSupport: !!document.createElement('video').canPlayType
              };
            }""")
        finally:
            page.close()
        expected = snapshot['descriptor']
        comparisons = {
            'userAgent': observed['userAgent'] == expected['user_agent'],
            'viewportWidth': observed['viewport']['width'] == expected['viewport']['width'],
            'viewportHeight': observed['viewport']['height'] == expected['viewport']['height'],
            'devicePixelRatio': abs(observed['devicePixelRatio'] - expected['device_scale_factor']) < 0.01,
            'touch': observed['maxTouchPoints'] > 0 if expected['has_touch'] else observed['maxTouchPoints'] == 0,
        }
        if 'screen' in expected:
            comparisons['screen'] = observed['screen'] == expected['screen']
        if locale:
            comparisons['language'] = observed['language'].lower() == locale.lower()

        # A mobile viewport/UA alone does not turn desktop Chromium into an
        # Android device. Report observable platform conflicts rather than
        # claiming the entire emulation matches the selected model.
        desktop_platforms = {'Win32', 'Win64', 'MacIntel', 'Linux x86_64',
                             'Linux i686', 'Linux x86'}
        android_preset = 'Android' in expected['user_agent']
        desktop_platform_with_mobile_ua = (
            android_preset and observed['platform'] in desktop_platforms
        )
        comparisons['platformCompatible'] = not desktop_platform_with_mobile_ua

        hints = observed['userAgentData']
        if hints is not None:
            comparisons['clientHintsMobile'] = hints['mobile'] is bool(expected['is_mobile'])
            if android_preset:
                comparisons['clientHintsPlatform'] = hints['platform'] == 'Android'

        warnings = [
            'Chromium no sistema operacional anfitrião; não é Android físico.',
            'WebGL e componentes multimídia são medidos, não falsificados.',
        ]
        if desktop_platform_with_mobile_ua:
            warnings.append('User-Agent Android com navigator.platform de desktop: '
                            'a emulação móvel não corresponde à plataforma real.')
        if hints is None:
            warnings.append('Client Hints indisponíveis; compatibilidade não verificada.')
        elif not comparisons.get('clientHintsMobile', True) or not comparisons.get('clientHintsPlatform', True):
            warnings.append('Client Hints observados divergem do dispositivo configurado.')
        if observed['webdriver'] is True:
            warnings.append('navigator.webdriver expõe controle automatizado do navegador.')
        if not all(comparisons.values()):
            warnings.append('Uma ou mais propriedades observadas divergem do preset.')
        warnings.append('Este diagnóstico não mede nem prevê o Suspect Score de sites externos.')
        return {
            'configured': {'preset': snapshot['preset'], 'version': snapshot['version'],
                           'playwright_version': snapshot['playwright_version'],
                           'descriptor': expected},
            'observed': observed,
            'user_agent_reference_audit': audit_mobile_user_agents(
                expected['user_agent'], observed['userAgent']),
            'comparisons': comparisons,
            'runtime_signals': {
                'automation_exposed': observed['webdriver'] is True,
                'desktop_platform_with_mobile_user_agent': desktop_platform_with_mobile_ua,
                'client_hints_available': hints is not None,
            },
            'consistent_for_tested_fields': all(comparisons.values()),
            'warnings': warnings,
            'limitations': ['HTTP Client Hints e IP externo não foram testados neste diagnóstico.',
                            'GPU, Canvas, AudioContext, fontes e WebRTC não são emulados.',
                            'A compatibilidade da plataforma verifica nomes comuns de desktop, '
                            'não a identidade física do aparelho.'],
        }
