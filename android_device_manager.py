"""Optional localhost backend for user-operated Android devices.

Uses official Android Debug Bridge to open an HTTP(S) URL on the selected
connected Android device, and scrcpy to mirror its screen. It never attaches
Playwright, patches browser APIs, or claims to alter anti-fraud results.
One physical Android is allowed to serve one active Nexora profile at a time;
a single device is NOT multiple isolated Android accounts.
"""
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from session_manager import SessionManager

SERIAL_RE = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


def executable(name, env):
    explicit = os.environ.get(env, '').strip().strip('"')
    if explicit:
        if Path(explicit).is_file():
            return str(Path(explicit))
        raise FileNotFoundError(f'{env} aponta para um executável inexistente.')
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(
        f'{name} não foi encontrado. Instale Android Platform Tools e scrcpy, '
        f'adicione-os ao PATH ou configure {env}.'
    )


class AndroidDeviceManager:
    """Maps a Nexus profile to one authorized, connected Android screen."""

    mode = 'android-real'

    def __init__(self, store):
        self.store = store
        self.sessions = SessionManager()
        self.mirrors = {}
        self.serials = {}

    def list_devices(self):
        adb = executable('adb', 'NEXORA_ADB_PATH')
        result = subprocess.run(
            [adb, 'devices'], capture_output=True, text=True,
            encoding='utf-8', timeout=12, check=True)
        devices = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if (len(parts) >= 2 and SERIAL_RE.fullmatch(parts[0])
                    and parts[1] in ('device', 'unauthorized', 'offline')):
                # ADB's well-known emulator serial is not a physical phone.
                # This is a preliminary check, not hardware attestation.
                emulator = parts[0].startswith('emulator-')
                devices.append({
                    'serial': parts[0], 'state': parts[1],
                    'emulator': emulator,
                    'available': parts[1] == 'device' and not emulator,
                })
        return devices

    def is_running(self, profile_id):
        process = self.mirrors.get(profile_id)
        if process is None:
            return False
        if process.poll() is None:
            return True
        self.mirrors.pop(profile_id, None)
        self.serials.pop(profile_id, None)
        self.sessions.stopped(profile_id)
        return False

    def start(self, profile_id, serial=None):
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Perfil não encontrado.')
        site = self.store.site(profile['site_id'])
        if site is None:
            raise ValueError('Site do perfil não encontrado.')
        if self.is_running(profile_id):
            return {'already_open': True, 'warning': None}
        active_devices = [d['serial'] for d in self.list_devices()
                          if d['available']]
        if not active_devices:
            raise ValueError('Nenhum Android físico autorizado encontrado. '
                             'Conecte o aparelho e aceite a depuração USB.')
        if serial is not None and (not isinstance(serial, str)
                                   or not SERIAL_RE.fullmatch(serial)):
            raise ValueError('Identificador Android inválido.')
        if serial is None:
            if len(active_devices) != 1:
                raise ValueError('Escolha o Android conectado que deseja usar.')
            serial = active_devices[0]
        if serial not in active_devices:
            raise ValueError('Android indisponível ou não autorizado.')
        for current, assigned in list(self.serials.items()):
            if self.is_running(current) and assigned == serial:
                raise ValueError('Esse Android já está vinculado a outra sessão '
                                 'aberta. Um aparelho não representa vários perfis independentes.')

        self.sessions.begin(profile_id, len(self.mirrors))
        try:
            adb = executable('adb', 'NEXORA_ADB_PATH')
            scrcpy = executable('scrcpy', 'NEXORA_SCRCPY_PATH')
            # ADB shell executes a command interpreter on the device. Quote
            # the stored URL for its remote shell; shell=False locally alone
            # does not protect characters like '&' within a URL.
            remote_command = ('am start -a android.intent.action.VIEW -d '
                              + shlex.quote(site['url']))
            subprocess.run(
                [adb, '-s', serial, 'shell', remote_command],
                capture_output=True, text=True, encoding='utf-8',
                timeout=15, check=True)
            process = subprocess.Popen(
                [scrcpy, '--serial=' + serial, '--no-audio',
                 '--window-title=' + 'Nexora Android - ' + profile['name'][:35]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            self.mirrors[profile_id] = process
            self.serials[profile_id] = serial
            self.sessions.running(profile_id)
            return {
                'already_open': False,
                'serial': serial,
                'warning': 'Android conectado: a navegação acontece no próprio '
                           'aparelho. Fechar o espelho não fecha o Chrome do celular.',
            }
        except Exception as exc:
            self.sessions.error(profile_id, exc)
            raise

    def stop(self, profile_id):
        if not self.is_running(profile_id):
            return False
        process = self.mirrors[profile_id]
        self.sessions.stopping(profile_id)
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        finally:
            self.mirrors.pop(profile_id, None)
            self.serials.pop(profile_id, None)
            self.sessions.stopped(profile_id)
        # The Android browser stays open, along with its real sessions.
        return True

    def stop_all(self):
        for profile_id in list(self.mirrors):
            self.stop(profile_id)

    def inspect(self, profile_id):
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Perfil não encontrado.')
        return {
            'profile': {'id': profile_id, 'name': profile['name']},
            'running': self.is_running(profile_id),
            'mode': self.mode,
            'configured': {
                'device_serial': self.serials.get(profile_id),
                'playwright_fingerprint_applied': False,
                'execution': 'android-device-browser',
            },
            'observed': None,
            'comparisons': None,
            'warnings': [
                'O navegador executa no Android conectado, não no computador.',
                'O preset móvel salvo para Playwright não é aplicado neste modo.',
                'O Nexora não modifica o fingerprint do aparelho.',
                'O sistema não mede nem garante Suspect Score de sites externos.',
                'Um Android não isola várias contas como se fossem aparelhos distintos.',
            ],
        }

    def session_details(self):
        return [self.sessions.describe(profile['id'], self.is_running(profile['id']))
                for profile in self.store.profiles]

    def status(self):
        return {profile['id']: ('running' if self.is_running(profile['id']) else 'stopped')
                for profile in self.store.profiles}
