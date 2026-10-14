"""Import *configuration only* from the user's LIXOCPA Multi-Login project.

This is an independently written compatibility adapter, not a copy of
LIXOCPA's account automation. Only public URL, requested mobile mode and
instance count are read. Ignore identities, saved accounts, proxy credentials,
extensions, banking fields and Chromium user profiles.
"""
from copy import deepcopy
from urllib.parse import urlsplit

from storage import validate_url, validate_device

MAX_URLS = 20
MAX_IMPORT_PROFILES = 200


def build_legacy_mobile_plan(configuration, device=None):
    if not isinstance(configuration, dict):
        raise ValueError('O settings.json deve conter um objeto JSON.')
    raw_urls = configuration.get('url', '')
    if not isinstance(raw_urls, str) or len(raw_urls) > 16000:
        raise ValueError('O campo url da configuração deve ser uma string.')
    urls = [value.strip() for value in raw_urls.split(',') if value.strip()]
    if not 1 <= len(urls) <= MAX_URLS:
        raise ValueError('Informe de 1 a 20 URLs para importar.')
    urls = [validate_url(u) for u in urls]
    if len(set(urls)) != len(urls):
        raise ValueError('Remova URLs duplicadas antes de importar.')

    mode = configuration.get('mode', 'celular')
    if not isinstance(mode, str) or mode.strip().lower() not in ('celular', 'app'):
        raise ValueError('Este importador mantém somente os modos mobile celular/app.')
    mode = mode.strip().lower()
    count = configuration.get('count', 1)
    if type(count) is not int or not 1 <= count <= 50:
        raise ValueError('O número de instâncias por site deve estar entre 1 e 50.')
    if len(urls) * count > MAX_IMPORT_PROFILES:
        raise ValueError('A importação está limitada a 200 novos perfis por vez.')

    selected_device = validate_device(device)
    warnings = [
        'Somente sites e configuração de perfis são importados.',
        'Cookies, contas, documentos, proxies, extensões e segredos não são importados.',
        'Os perfis usam o preset Android do Nexora; não copiam os scripts do LIXOCPA.',
    ]
    if mode == 'app':
        warnings.append('Modo app/WebView não é reproduzido: será usado Chromium mobile emulado.')
    return {'mode': mode, 'count_per_url': count, 'urls': urls,
            'profiles_to_create': len(urls) * count,
            'device': selected_device, 'warnings': warnings}


def import_legacy_mobile_settings(store, configuration, device=None):
    plan = build_legacy_mobile_plan(configuration, device)
    # The UI requires explicit confirmation. This backend function assumes it.
    old_sites = deepcopy(store.sites)
    old_profiles = deepcopy(store.profiles)
    created_sites, created_profiles = [], []
    try:
        for site_url in plan['urls']:
            site = next((item for item in store.sites if item['url'] == site_url), None)
            if site is None:
                host = urlsplit(site_url).hostname or 'Site'
                label = ('LIXOCPA - ' + host)[:80]
                site = store.create_site(label, site_url)
                created_sites.append(site['id'])
            for number in range(1, plan['count_per_url'] + 1):
                name = f"LIXOCPA {host if site_url in plan['urls'] else 'mobile'} #{number:02}"
                # Existing records retain their IDs. A new imported instance
                # always receives a fresh Chrome directory and snapshot.
                created = store.create_profile(name[:80], site['id'], plan['device'])
                created_profiles.append(created['id'])
    except Exception:
        store.sites = old_sites
        store.profiles = old_profiles
        store.save()
        raise
    return {'sites_created': len(created_sites),
            'profiles_created': len(created_profiles),
            'profile_ids': created_profiles,
            'warnings': plan['warnings'],
            'note': 'Importação de metadados concluída; nenhuma sessão importada ou iniciada.'}
