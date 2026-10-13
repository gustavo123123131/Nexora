"""Start the Windows Chromium executor and a free, temporary Cloudflare Tunnel.

Only launched by INICIAR_EXECUTOR_WINDOWS.bat. Does not change old data/.
The generated secret and Chromium profiles stay in ignored runner/ folders.
"""
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parent
PRIVATE = HOME / 'private'
PROFILE_DIR = HOME / 'data' / 'profiles'
PORT = 8765
HEALTH = f'http://127.0.0.1:{PORT}/healthz'
TUNNEL_PATTERN = re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com\b', re.I)
ORIGIN = 'https://nexora-ebon-eight.vercel.app'


def cloudflared_binary():
    found = shutil.which('cloudflared') or shutil.which('cloudflared.exe')
    if found:
        return found
    paths = [
        Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'cloudflared' / 'cloudflared.exe',
        Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'cloudflared' / 'cloudflared.exe',
        HOME / 'cloudflared.exe',
    ]
    return str(next((p for p in paths if p.is_file()), ''))


def secret_key():
    path = PRIVATE / 'runner-key.txt'
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        # Exclusive create; never replace existing credentials or profile data.
        with path.open('x', encoding='utf-8') as file:
            file.write(secrets.token_urlsafe(48) + '\n')
    value = path.read_text(encoding='utf-8').strip()
    if len(value) < 32:
        raise RuntimeError(f'A chave em {path} e curta. Corrija sem apagar os seus dados.')
    return value


def wait_health(process, seconds=35):
    for _ in range(seconds * 4):
        if process.poll() is not None:
            raise RuntimeError('Servidor Chromium encerrou antes de iniciar. Confira runner/private/worker.log.')
        try:
            with urllib.request.urlopen(HEALTH, timeout=0.8) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError('Servidor Chromium nao respondeu. Confira runner/private/worker.log.')


def _read_tunnel(stream, events):
    try:
        for line in stream:
            match = TUNNEL_PATTERN.search(line)
            if match:
                events.put(('url', match.group(0)))
            elif any(term in line.lower() for term in ['error', 'failed', 'unable']):
                events.put(('log', line.strip()[:240]))
    finally:
        events.put(('finished', ''))


def _stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    print('\n====== NEXORA | EXECUTOR WINDOWS + CLOUDFLARE GRATIS ======\n', flush=True)
    if os.name != 'nt':
        print('Este iniciador e especifico para Windows.')
        return 1

    cloudflared = cloudflared_binary()
    if not cloudflared:
        print('Cloudflare Tunnel nao encontrado. Instale cloudflared com:\n')
        print('    winget install -e --id Cloudflare.cloudflared\n')
        print('Depois feche e abra novamente o iniciador.')
        return 1

    # Do not terminate or take over an already-running service on this port.
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', PORT))
        except OSError:
            print(f'A porta {PORT} ja esta em uso. Feche o outro executor antes de iniciar.')
            return 1

    key = secret_key()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.update({
        'NEXORA_RUNNER_KEY': key,
        'NEXORA_PROFILE_DIR': str(PROFILE_DIR),
        'NEXORA_PANEL_ORIGIN': ORIGIN,
        'NEXORA_MAX_PROFILES': '3',
        'NEXORA_BIND': '127.0.0.1',
        'PORT': str(PORT),
        'PYTHONUNBUFFERED': '1',
    })

    worker = None
    tunnel = None
    try:
        log_file = PRIVATE / 'worker.log'
        with log_file.open('a', encoding='utf-8') as logs:
            worker = subprocess.Popen([sys.executable, str(HOME / 'worker.py')],
                                      cwd=str(HOME), env=environment,
                                      stdin=subprocess.DEVNULL, stdout=logs, stderr=subprocess.STDOUT)
            print('Iniciando Chromium local...', flush=True)
            wait_health(worker)

            # Quick Tunnel uses no account, credit card or paid domain.
            events = queue.Queue()
            tunnel = subprocess.Popen([cloudflared, 'tunnel', '--url', HEALTH.removesuffix('/healthz'),
                                       '--no-autoupdate'],
                                      cwd=str(HOME), stdin=subprocess.DEVNULL,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace')
            reader = threading.Thread(target=_read_tunnel, args=(tunnel.stdout, events), daemon=True)
            reader.start()
            public_url = None
            last_error = None
            deadline = time.monotonic() + 80
            while time.monotonic() < deadline and not public_url:
                if tunnel.poll() is not None:
                    break
                try:
                    kind, value = events.get(timeout=1)
                except queue.Empty:
                    continue
                if kind == 'url':
                    public_url = value
                elif kind == 'log':
                    last_error = value

            if not public_url:
                print('Cloudflare nao gerou uma URL. Confira a internet e o cloudflared.')
                if last_error:
                    print('Detalhe:', last_error)
                return 1

            print('\n' + '=' * 60)
            print('URL DO TUNEL (cole em Conectar navegador no Nexora):')
            print(public_url)
            print('\nCHAVE PRIVADA (cole no segundo campo, NAO COMPARTILHE):')
            print(key)
            print('\nPainel: ' + ORIGIN)
            print('O Windows precisa ficar ligado e esta janela aberta.')
            print('Ao reiniciar o tunel a URL muda, mas os perfis permanecem salvos.')
            print('Para encerrar, aperte Ctrl+C aqui; feche os perfis antes.')
            print('=' * 60 + '\n', flush=True)

            while True:
                if worker.poll() is not None:
                    print('Servidor Chromium encerrou. Confira runner/private/worker.log.')
                    return 1
                if tunnel.poll() is not None:
                    print('Cloudflare Tunnel desconectou. Inicie novamente para gerar outra URL.')
                    return 1
                time.sleep(2)
    except KeyboardInterrupt:
        print('\nEncerrando o tunel e o executor. Prefira encerrar perfis pelo Nexora.')
        return 0
    except (RuntimeError, OSError) as error:
        print('Erro:', str(error))
        return 1
    finally:
        _stop(tunnel)
        _stop(worker)


if __name__ == '__main__':
    raise SystemExit(main())
