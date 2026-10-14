"""Persistência local simples e atômica; nunca salva cookies no JSON."""
import json
import os
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
from fingerprint_manager import FingerprintManager

# Match the signed-off Playwright device catalog used by the Windows runner.
_CATALOG_PATH = Path(__file__).resolve().parent / 'runner' / 'device_catalog.json'
_DEVICE_CATALOG = json.loads(_CATALOG_PATH.read_text(encoding='utf-8'))
DEVICE_MODELS = frozenset(_DEVICE_CATALOG['devices'])
DEFAULT_DEVICE = _DEVICE_CATALOG['default_device']


def validate_device(value):
    if value is None:
        return DEFAULT_DEVICE
    if not isinstance(value, str) or value not in DEVICE_MODELS:
        raise ValueError('Selecione um modelo de dispositivo válido.')
    return value


def validate_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Informe uma URL válida com até 2048 caracteres.')
    value = value.strip()
    if any(ord(ch) < 32 for ch in value) or '\\' in value:
        raise ValueError('A URL contém caracteres inválidos.')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as ex:
        raise ValueError('A URL tem uma porta ou formato inválido.') from ex
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use uma URL http:// ou https://, sem usuário e senha embutidos.')
    if parsed.hostname.endswith('.') or ' ' in parsed.netloc or (port is not None and port == 0):
        raise ValueError('O domínio ou a porta informados são inválidos.')
    return value


def validate_name(name, label='nome'):
    if not isinstance(name, str):
        raise ValueError(f'Informe o {label}.')
    clean = name.strip()
    if not 1 <= len(clean) <= 80 or any(ord(ch) < 32 for ch in clean):
        raise ValueError(f'O {label} deve ter de 1 a 80 caracteres.')
    return clean


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'settings.json'
        self.profiles_dir = self.root / 'profiles'
        self.profiles_dir.mkdir(exist_ok=True)
        if self.path.exists():
            with self.path.open('r', encoding='utf-8') as fp:
                value = json.load(fp)
            self.sites = value['sites']
            self.profiles = value['profiles']
            # Non-destructive migration of legacy records: the selected model
            # remains identical and each profile receives a pinned snapshot.
            changed = False
            for profile in self.profiles:
                if 'fingerprint' not in profile:
                    profile['device'] = validate_device(profile.get('device'))
                    profile['fingerprint'] = FingerprintManager.generate(
                        profile['device'], reason='legacy-migration')
                    changed = True
            if changed:
                self.save()
        else:
            self.sites, self.profiles = [], []
            self.save()

    def save(self):
        temp = self.path.with_suffix('.tmp')
        with temp.open('w', encoding='utf-8') as fp:
            json.dump({'sites': self.sites, 'profiles': self.profiles}, fp, ensure_ascii=False, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp, self.path)

    def site(self, site_id):
        return next((item for item in self.sites if item['id'] == site_id), None)

    def profile(self, profile_id):
        return next((item for item in self.profiles if item['id'] == profile_id), None)

    def create_site(self, name, url):
        item = {'id': uuid4().hex, 'name': validate_name(name), 'url': validate_url(url)}
        self.sites.append(item)
        self.save()
        return item

    def update_site(self, site_id, name, url):
        item = self.site(site_id)
        if item is None:
            raise LookupError('Site não encontrado.')
        item.update(name=validate_name(name), url=validate_url(url))
        self.save()
        return item

    def delete_site(self, site_id):
        if any(p['site_id'] == site_id for p in self.profiles):
            raise ValueError('Este site está vinculado a perfis. Exclua os perfis primeiro.')
        if not self.site(site_id):
            raise LookupError('Site não encontrado.')
        self.sites = [s for s in self.sites if s['id'] != site_id]
        self.save()

    def create_profile(self, name, site_id, device=None):
        if not self.site(site_id):
            raise ValueError('Selecione um site cadastrado.')
        selected = validate_device(device)
        item = {'id': uuid4().hex, 'name': validate_name(name, 'nome do perfil'),
                'site_id': site_id, 'device': selected,
                'fingerprint': FingerprintManager.generate(selected),
                'instance_id': 'local-default'}
        self.profiles.append(item)
        self.save()
        return item

    def update_profile(self, profile_id, name, site_id, device=None):
        item = self.profile(profile_id)
        if item is None:
            raise LookupError('Perfil não encontrado.')
        if not self.site(site_id):
            raise ValueError('Selecione um site cadastrado.')
        new_name = validate_name(name, 'nome do perfil')
        new_device = validate_device(device)
        if new_device != item.get('device'):
            # Changing model explicitly also selects a different official
            # emulation descriptor. Do not regenerate on ordinary rename.
            item['fingerprint'] = FingerprintManager.generate(
                new_device, reason='user-changed-device')
        item.update(name=new_name, site_id=site_id, device=new_device)
        self.save()
        return item

    def duplicate_profile(self, profile_id):
        original = self.profile(profile_id)
        if original is None:
            raise LookupError('Perfil não encontrado.')
        base = original['name']
        suffix = ' (cópia)'
        return self.create_profile(base[:80 - len(suffix)] + suffix,
                                   original['site_id'], original.get('device'))

    def regenerate_fingerprint(self, profile_id):
        original = self.profile(profile_id)
        if original is None:
            raise LookupError('Perfil não encontrado.')
        selected = validate_device(original.get('device'))
        original['fingerprint'] = FingerprintManager.generate(
            selected, reason='user-explicit-regeneration')
        self.save()
        return original

    def delete_profile(self, profile_id):
        if not self.profile(profile_id):
            raise LookupError('Perfil não encontrado.')
        self.profiles = [p for p in self.profiles if p['id'] != profile_id]
        self.save()
