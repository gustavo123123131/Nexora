"""Cada perfil usa um diretório Chromium e um processo independente."""
import os
import locale
import re
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from fingerprint_manager import FingerprintManager
from session_manager import SessionManager
from window_layout_manager import WindowLayoutManager


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
        self.sessions = SessionManager()
        self.window_layouts = WindowLayoutManager(self.store.profiles_dir.parent)

    def _playwright(self):
        if self.playwright is None:
            self.playwright = sync_playwright().start()
        return self.playwright

    def _session_cookie_path(self, profile_id):
        return self.store.profiles_dir / profile_id / '.nexora-session-cookies.json'

    def _save_session_cookies(self, context, profile_id):
        """Atomically back up session cookies before the browser is closed."""
        path = self._session_cookie_path(profile_id)
        contents = json.dumps(context.cookies(), ensure_ascii=False).encode('utf-8')
        temp = path.with_suffix('.tmp')
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()

    def _restore_session_cookies(self, context, profile_id):
        path = self._session_cookie_path(profile_id)
        if not path.exists():
            return
        cookies = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(cookies, list):
            raise ValueError('Backup de cookies inválido.')
        prepared = []
        for original in cookies:
            if not isinstance(original, dict):
                raise ValueError('Cookie inválido no backup.')
            cookie = dict(original)
            if cookie.get('expires', 0) <= 0:
                cookie.pop('expires', None)
            prepared.append(cookie)
        if prepared:
            context.add_cookies(prepared)

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
            self.sessions.stopped(profile_id)
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
        fingerprint = FingerprintManager.validate(profile.get('fingerprint'),
                                                  profile.get('device', 'Pixel 7'))
        options = FingerprintManager.apply(pw, fingerprint)
        viewport = options['viewport']
        directory = self.store.profiles_dir / profile_id
        directory.mkdir(exist_ok=True)
        bounds = None
        if os.name == 'nt' and not self.headless:
            try:
                bounds = self.window_layouts.get(profile_id)
            except ValueError as error:
                if os.environ.get('MULTILOGIN_VERBOSE') == '1':
                    print('[layout] Configuração de janela inválida:', type(error).__name__)
        window_args = ([f"--window-position={bounds['left']},{bounds['top']}",
                        f"--window-size={bounds['width']},{bounds['height']}"]
                       if bounds else
                       [f"--window-size={viewport['width'] + 150},{viewport['height'] + 155}"])
        options.update(
            headless=self.headless,
            accept_downloads=True,
            # Follow the machine's locale and timezone instead of imposing
            # a different geographic environment on every local profile.
            args=window_args,
        )
        language = _local_os_language()
        if language:
            options['locale'] = language
        if self.executable_path:
            options['executable_path'] = self.executable_path
        self.sessions.begin(profile_id, len(self.contexts))
        self.starting.add(profile_id)
        context = None
        try:
            context = pw.chromium.launch_persistent_context(str(directory), **options)
            self._restore_session_cookies(context, profile_id)
            self.contexts[profile_id] = context
            context.on('close', lambda *args: self.contexts.pop(profile_id, None)
                       if self.contexts.get(profile_id) is context else None)
            page = context.pages[0] if context.pages else context.new_page()
            if bounds is not None:
                try:
                    self.window_layouts.apply_to_context(context, bounds)
                except Exception:
                    # Window placement is optional: never fail the mobile
                    # browser launch or the user's saved session over it.
                    if os.environ.get('MULTILOGIN_VERBOSE') == '1':
                        print('[layout] Não foi possível restaurar a posição da janela.')
            warning = None
            try:
                page.goto(site['url'], wait_until='domcontentloaded', timeout=15000)
            except PlaywrightError as ex:
                if os.environ.get('MULTILOGIN_VERBOSE') == '1':
                    print('Aviso de navegacao:', repr(ex))
                warning = 'Janela aberta, mas o site não carregou. Confira a URL, a conexão e eventuais restrições do navegador.'
            self.sessions.running(profile_id)
            return {'already_open': False, 'warning': warning}
        except Exception as exc:
            self.sessions.error(profile_id, exc)
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self.contexts.pop(profile_id, None)
            raise
        finally:
            self.starting.discard(profile_id)

    def inspect(self, profile_id):
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Perfil não encontrado.')
        snapshot = FingerprintManager.validate(profile.get('fingerprint'),
                                               profile.get('device', 'Pixel 7'))
        if not self.is_running(profile_id):
            return {
                'profile': {'id': profile_id, 'name': profile['name']},
                'running': False,
                'configured': snapshot,
                'observed': None,
                'comparisons': None,
                'warnings': ['Abra o navegador do perfil para medir o fingerprint real.'],
            }
        result = FingerprintManager.inspect(self.contexts[profile_id],
                                             snapshot, locale=_local_os_language())
        result['profile'] = {'id': profile_id, 'name': profile['name']}
        result['running'] = True
        return result

    def save_window_position(self, profile_id):
        if os.name != 'nt' or self.headless:
            raise ValueError('Salvamento de posições exige Chromium visível no Windows.')
        if not self.is_running(profile_id):
            raise ValueError('Abra o perfil antes de salvar sua posição.')
        context = self.contexts[profile_id]
        bounds = self.window_layouts.read_window(context)
        return self.window_layouts.save(profile_id, bounds)

    def stop(self, profile_id):
        if os.name == 'nt' and not self.headless and profile_id in self.contexts:
            try:
                self.save_window_position(profile_id)
            except Exception:
                # Do not allow window-position metadata to prevent saving
                # session cookies or gracefully closing an active browser.
                pass
        context = self.contexts.pop(profile_id, None)
        if context is None:
            return False
        self.sessions.stopping(profile_id)
        try:
            self._save_session_cookies(context, profile_id)
        except PlaywrightError:
            pass  # Browser was already closed manually.
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass
            self.sessions.stopped(profile_id)
        return True

    def stop_all(self):
        for profile_id in list(self.contexts):
            self.stop(profile_id)
        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None

    def session_details(self):
        return [self.sessions.describe(profile['id'], self.is_running(profile['id']))
                for profile in self.store.profiles]

    def status(self):
        return {profile['id']: ('running' if self.is_running(profile['id']) else 'stopped')
                for profile in self.store.profiles}
