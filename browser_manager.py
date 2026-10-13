"""Cada perfil usa um diretório Chromium e um processo independente."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError


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
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
            args=['--window-size=480,980'],
        )
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
