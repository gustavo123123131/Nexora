"""Local device-profile lifecycle. Coordinates stored metadata and real browsers.

Only the user's local default instance exists today. Copying a configuration
never copies another profile's cookies, storage, tokens or browser directory.
"""
import re
import shutil

from fingerprint_manager import FingerprintManager

ID = re.compile(r'^[0-9a-f]{32}$')


class DeviceProfileManager:
    def __init__(self, store, browser_manager):
        self.store = store
        self.browsers = browser_manager

    def create(self, name, site_id, device=None):
        return self.store.create_profile(name, site_id, device)

    def get(self, profile_id):
        if not isinstance(profile_id, str) or not ID.fullmatch(profile_id):
            raise ValueError('ID de dispositivo inválido.')
        profile = self.store.profile(profile_id)
        if profile is None:
            raise LookupError('Dispositivo não encontrado.')
        return profile

    def list(self):
        return self.store.profiles

    def update(self, profile_id, name, site_id, device=None):
        self.get(profile_id)
        if self.browsers.is_running(profile_id):
            raise ValueError('Encerre o navegador antes de editar seu dispositivo.')
        return self.store.update_profile(profile_id, name, site_id, device)

    def duplicate_configuration(self, profile_id):
        self.get(profile_id)
        return self.store.duplicate_profile(profile_id)

    def regenerate(self, profile_id, confirmed=False):
        self.get(profile_id)
        if confirmed is not True:
            raise ValueError('Confirmação explícita obrigatória.')
        if self.browsers.is_running(profile_id):
            raise ValueError('Encerre o navegador antes de atualizar o snapshot.')
        return self.store.regenerate_fingerprint(profile_id)

    def export_configuration(self, profile_id):
        profile = self.get(profile_id)
        FingerprintManager.validate(profile['fingerprint'], profile['device'])
        return {
            'schema_version': 1,
            'name': profile['name'],
            'site_id': profile['site_id'],
            'device': profile['device'],
            'fingerprint': profile['fingerprint'],
            'note': 'Somente preferências; não inclui cookies, senhas ou armazenamento.',
        }

    def import_configuration(self, data):
        if not isinstance(data, dict) or data.get('schema_version') != 1:
            raise ValueError('Arquivo de configuração inválido.')
        FingerprintManager.validate(data.get('fingerprint'), data.get('device'))
        # Explicitly create fresh snapshot, ID and empty storage instead of
        # treating an exported browser identity as a session clone.
        return self.create(data.get('name'), data.get('site_id'), data.get('device'))

    def delete(self, profile_id):
        self.get(profile_id)
        self.browsers.stop(profile_id)
        self.store.delete_profile(profile_id)
        directory = self.store.profiles_dir / profile_id
        if directory.is_dir():
            shutil.rmtree(directory)
