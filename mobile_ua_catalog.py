"""Read-only audit of user-provided mobile User-Agent reference strings.

The reference list does NOT configure Chromium. A User-Agent string cannot
replace the browser engine, operating system, GPU, Client Hints or automation
state. The existing mobile Playwright descriptors remain the source of truth.
"""
import json
import re
from collections import Counter
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parent / 'reference' / '__mobile_userAgent.json'
CHROME_VERSION = re.compile(r'\bChrome/(\d+\.\d+\.\d+\.\d+)\b')


def _chrome_version(user_agent):
    match = CHROME_VERSION.search(user_agent)
    return match.group(1) if match else None


def audit_mobile_user_agents(expected_user_agent, observed_user_agent=None, *, path=None):
    """Describe compatibility of a UA list against a real Chromium profile.

    Never chooses or installs a UA; only compares data that already exist.
    No cookies, browsing history, tokens, IP address or external calls.
    """
    if not isinstance(expected_user_agent, str):
        raise ValueError('User-Agent esperado inválido.')
    if observed_user_agent is not None and not isinstance(observed_user_agent, str):
        raise ValueError('User-Agent observado inválido.')
    path = Path(path) if path is not None else DEFAULT_CATALOG
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError('Catálogo de User-Agents excede 1 MB.')
        data = json.loads(path.read_text(encoding='utf-8'))
        agents = data['userAgents']
        if (not isinstance(agents, list) or len(agents) > 10000 or
                any(not isinstance(agent, str) or len(agent) > 512
                    for agent in agents)):
            raise ValueError('Lista de User-Agents inválida.')
    except FileNotFoundError:
        return {'available': False, 'applied_to_browser': False,
                'note': 'Catálogo de User-Agents não encontrado.'}
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {'available': False, 'applied_to_browser': False,
                'note': 'O arquivo de referências não pôde ser validado.'}

    android = [agent for agent in agents if 'Android' in agent]
    iphone = [agent for agent in agents if 'iPhone;' in agent]
    version_counts = Counter(v for agent in android
                             if (v := _chrome_version(agent)) is not None)
    reference_version = _chrome_version(expected_user_agent)
    same_engine_build = version_counts.get(reference_version, 0) if reference_version else 0
    major = reference_version.split('.')[0] if reference_version else None
    same_major = sum(count for name, count in version_counts.items()
                     if name.split('.')[0] == major)
    expected_is_android = 'Android' in expected_user_agent
    observation = {
        'available': True,
        'applied_to_browser': False,
        'total_entries': len(agents),
        'unique_entries': len(set(agents)),
        'duplicates': len(agents) - len(set(agents)),
        'android_entries': len(android),
        'iphone_safari_entries': len(iphone),
        'reference_chrome_versions': dict(sorted(version_counts.items())),
        'configured_chrome_version': reference_version,
        'configured_ua_present_in_list': expected_user_agent in agents,
        'same_chrome_build_entries': same_engine_build,
        'same_chrome_major_entries': same_major,
        'configured_engine_is_android_chromium': expected_is_android and reference_version is not None,
        'notes': [
            'Referências não aplicadas: o preset mobile persistente do Playwright foi preservado.',
            'User-Agent isolado não altera o navegador real, Client Hints ou navigator.webdriver.',
        ],
    }
    if observed_user_agent is not None:
        observation['observed_ua_present_in_list'] = observed_user_agent in agents
        observation['observed_equals_configured'] = observed_user_agent == expected_user_agent
    if iphone:
        observation['notes'].append(
            'A lista contém Safari de iPhone: não corresponde ao mecanismo Chromium Android.')
    if not same_engine_build and reference_version:
        observation['notes'].append(
            'Nenhuma entrada corresponde à versão completa de Chrome declarada pelo perfil.')
    return observation
