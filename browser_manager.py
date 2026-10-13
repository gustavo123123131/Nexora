"""Cada perfil usa um diretório Chromium e um processo independente."""
import os
import locale
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError


def _local_os_language():
    # Legacy local launcher: keep Accept-Language aligned with Windows.
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
            value = buffer.value
            if re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value):
                return value
    try:
        value = locale.getlocale()[0]
    except (TypeError, ValueError):
        value = None
    if value:
        value = value.replace('_', '-')
        if re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value):
            return value
    # Chromium defaults to en-US under the POSIX C locale.
    return 'en-US'


class BrowserManager:
    def __init__(self, store, *, headless=None, executable_path=None):
        self.store = store
        self.headless = (os.environ.get('MULTILOGIN_HEADLESS') == '1') if headless is None else headless
        self.executable_path = executable_path or os.environ.get('MULTILOGIN_CHROMIUM_PATH') or None
        self.playwright = None
        self.contexts = {}
        self.starting = set()

    def _playwright(self):
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        return self.playwright

    def is_running(self, profile_id):
        context = self.contexts.get(profile_id)
        if context is None:
            return False
        try:
            # Força uma chamada ao Chromium para detectar fechamento manual.
            context.cookies()
            return True
        except PlaywrightError:
            self.contexts.pop(profile_id, None)
            return False

    def start(self, profile_id):
        profile = self.store.profile(profile_id)
        if not profile:
            raise LookupError('Perfil não encontrado.')
        site = self.store.site(profile['site_id'])
        if not site:
            raise ValueError('O site desse perfil não existe mais.')
        if self.is_running(profile_id):
            return {'already_open': True, 'warning': None}
        pw = self._playwright()
        device = pw.devices['Pixel 7']
        directory = self.store.profiles_dir / profile_id
        directory.mkdir(exist_ok=True)
        options = {key: value for key, value in device.items() if key != 'default_browser_type'}
        options.update(
            headless=self.headless,
            accept_downloads=True,
            # Follow the machine's locale and timezone instead of imposing
            # a different geographic environment on every local profile.
            args=[f"--window-size={device['viewport']['width'] + 150},{device['viewport']['height'] + 155}"],
        )
        language = _local_os_language()
        if language:
            options['locale'] = language
        if self.executable_path:
            options['executable_path'] = self.executable_path
        self.starting.add(profile_id)
        context = None
        try:
            context = pw.chromium.launch_persistent_context(str(directory), **options)
            self.contexts[profile_id] = context
            context.on('close', lambda *args: self.contexts.pop(profile_id, None)
                       if self.contexts.get(profile_id) is context else None)
            page = context.pages[0] if context.pages else context.new_page()
            warning = None
            try:
                page.goto(site['url'], wait_until='domcontentloaded', timeout=15000)
            except PlaywrightError as ex:
                if os.environ.get('MULTILOGIN_VERBOSE') == '1':
                    print('Aviso de navegacao:', repr(ex))
                warning = 'Janela aberta, mas o site não carregou. Confira a URL, a conexão e eventuais restrições do navegador.'
            return {'already_open': False, 'warning': warning}
        except Exception:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self.contexts.pop(profile_id, None)
            raise
        finally:
            self.starting.discard(profile_id)

    def stop(self, profile_id):
        context = self.contexts.pop(profile_id, None)
        if context is None:
            return False
        try:
            context.close()
        except PlaywrightError:
            pass
        return True

    def stop_all(self):
        for profile_id in list(self.contexts):
            self.stop(profile_id)
        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None

    def status(self):
        return {profile['id']: ('running' if self.is_running(profile['id']) else 'stopped')
                for profile in self.store.profiles}
