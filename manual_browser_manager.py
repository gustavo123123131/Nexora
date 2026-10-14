"""Optional localhost mode: open the user's installed Chrome without automation.

This does not spoof fingerprints, launch Playwright, attach a debugger or
intercept page APIs. The user controls and closes the native Chrome windows.
Local Chromium/Playwright mode remains the default and is unchanged.
"""
import os
import shutil
import subprocess
from pathlib import Path

from session_manager import SessionManager


def find_chrome():
    explicit = os.environ.get('MULTILOGIN_CHROME_PATH', '').strip().strip('"')
    if explicit:
        if Path(explicit).is_file():
            return str(Path(explicit))
        raise FileNotFoundError('MULTILOGIN_CHROME_PATH aponta para um arquivo inexistente.')

    candidates = []
    if os.name == 'nt':
        for base in (os.environ.get('PROGRAMFILES'),
                     os.environ.get('PROGRAMFILES(X86)'),
                     os.environ.get('LOCALAPPDATA')):
            if base:
                candidates.append(Path(base) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe')
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    executable = shutil.which('google-chrome') or shutil.which('google-chrome-stable') or shutil.which('chrome')
    if executable:
        return executable
    raise FileNotFoundError(
        'Google Chrome não encontrado. Instale Chrome ou configure MULTILOGIN_CHROME_PATH.'
    )


class ManualChromeManager:
    """A native, human-operated Chrome process with separate storage per profile."""

    mode = 'chrome-manual'

    def __init__(self, store, *, executable_path=None):
        self.store = store
        self.executable_path = executable_path
        self.processes = {}
        self.sessions = SessionManager()

    def is_running(self, profile_id):
        process = self.processes.get(profile_id)
        if process is None:
            return False
        if process.poll() is None:
            return True
        self.processes.pop(profile_id, None)
        self.sessions.stopped(profile_id)
        return False

    def start(self, profile_id):
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Perfil não encontrado.')
        site = self.store.site(profile['site_id'])
        if site is None:
            raise ValueError('Site do perfil não encontrado.')
        if self.is_running(profile_id):
            return {'already_open': True, 'warning': None}

        self.sessions.begin(profile_id, sum(self.is_running(pid) for pid in list(self.processes)))
        try:
            executable = self.executable_path or find_chrome()
            directory = self.store.profiles_dir / profile_id / 'chrome-manual'
            directory.mkdir(parents=True, exist_ok=True)
            # Separate native Chrome storage. Never use Playwright's profile
            # folder, copy cookies, or pass automation/remote-debugging flags.
            process = subprocess.Popen(
                [executable, '--user-data-dir=' + str(directory),
                 '--new-window', site['url']],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, shell=False,
            )
            self.processes[profile_id] = process
            self.sessions.running(profile_id)
            return {'already_open': False,
                    'warning': 'Modo manual: Chrome desktop real, sem emulação Android. '
                               'Feche a janela do Chrome para encerrar o perfil.'}
        except Exception as error:
            self.sessions.error(profile_id, error)
            raise

    def stop(self, profile_id):
        if self.is_running(profile_id):
            raise ValueError('Modo manual: feche a janela do Chrome. '
                             'O Nexora não força o encerramento para proteger seus dados.')
        return False

    def stop_all(self):
        # Native Chrome belongs to the user, not to the panel's lifetime.
        # The user may keep their browser open after exiting localhost.
        pass

    def inspect(self, profile_id):
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Perfil não encontrado.')
        return {
            'profile': {'id': profile_id, 'name': profile['name']},
            'running': self.is_running(profile_id),
            'mode': self.mode,
            'configured': {'chrome_profile_directory': str(
                self.store.profiles_dir / profile_id / 'chrome-manual'),
                'mobile_preset_applied': False},
            'observed': None,
            'comparisons': None,
            'warnings': [
                'Chrome nativo sem Playwright ou injeções. O usuário navega manualmente.',
                'Preset Android cadastrado não é aplicado neste modo.',
                'Inspeção automática indisponível, pois não há conexão de automação.',
                'Não há garantia de resultado específico em detectores externos.'
            ]
        }

    def session_details(self):
        return [self.sessions.describe(profile['id'], self.is_running(profile['id']))
                for profile in self.store.profiles]

    def status(self):
        return {profile['id']: ('running' if self.is_running(profile['id']) else 'stopped')
                for profile in self.store.profiles}
