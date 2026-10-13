"""Nexora remote Chromium worker. Runs on a persistent Linux container, NOT Vercel.

All browser state is isolated under NEXORA_PROFILE_DIR/<profile-id>.
Remote control uses a high-entropy secret; do not publish it to client code.
"""
import hmac
import ipaddress
import os
import queue
import re
import threading
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request
from playwright.sync_api import sync_playwright, Error as PlaywrightError

app = Flask(__name__)
ID_RE = re.compile(r'^[0-9a-f]{32}$')
KEYS = {'Enter', 'Tab', 'Backspace', 'Escape', 'ArrowUp', 'ArrowDown',
        'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Delete', 'ControlOrMeta+A'}
STORE = Path(os.environ.get('NEXORA_PROFILE_DIR', '/data/profiles'))
MAX_PROFILES = max(1, min(6, int(os.environ.get('NEXORA_MAX_PROFILES', '3'))))


def valid_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError('ID de perfil inválido.')
    return value


def valid_url(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 2048 or any(ord(c) < 33 for c in value):
        raise ValueError('URL inválida.')
    p = urlsplit(value)
    try:
        _port = p.port
    except ValueError:
        raise ValueError('Porta inválida.')
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('A URL deve ser HTTP(S), sem credenciais.')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Endereço local não permitido.')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('IP privado ou reservado não permitido.')
    except ValueError as exc:
        if 'não permitido' in str(exc):
            raise
    return value


class BrowserWorker:
    """All Playwright calls run on ONE dedicated Python thread."""
    def __init__(self):
        self.jobs = queue.Queue()
        self.contexts = {}
        self.thread = threading.Thread(target=self._serve, daemon=True, name='playwright-worker')
        self.thread.start()

    def _serve(self):
        playwright = None
        try:
            while True:
                func, args, future = self.jobs.get()
                if future.cancelled():
                    continue
                try:
                    if playwright is None:
                        playwright = sync_playwright().start()
                    value = getattr(self, func)(playwright, *args)
                    future.set_result(value)
                except BaseException as exc:
                    future.set_exception(exc)
        finally:
            for context in self.contexts.values():
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                playwright.stop()

    def run(self, func, *args):
        future = Future()
        self.jobs.put((func, args, future))
        return future.result(timeout=30)

    def page(self, pid):
        context = self.contexts.get(pid)
        if context is None:
            raise LookupError('Perfil parado. Clique em Abrir.')
        if context.pages:
            pages = [p for p in context.pages if not p.is_closed()]
            if pages:
                return pages[-1]
        return context.new_page()

    def status(self, pw, pid):
        context = self.contexts.get(pid)
        if context is None:
            return {'running': False}
        try:
            context.cookies()
            return {'running': True}
        except PlaywrightError:
            self.contexts.pop(pid, None)
            return {'running': False}

    def start(self, pw, pid, url):
        if self.status(pw, pid)['running']:
            return {'running': True, 'already_open': True}
        if len(self.contexts) >= MAX_PROFILES:
            raise ValueError(f'Limite de {MAX_PROFILES} navegadores simultâneos.')
        STORE.mkdir(parents=True, exist_ok=True)
        profile_dir = STORE / pid
        profile_dir.mkdir(exist_ok=True)
        opts = {k: v for k, v in pw.devices['Pixel 7'].items()
                if k != 'default_browser_type'}
        opts.update(headless=True, locale='pt-BR', accept_downloads=False,
                    args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = pw.chromium.launch_persistent_context(str(profile_dir), **opts)
        self.contexts[pid] = context
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(8000)
            page.goto(url, wait_until='domcontentloaded', timeout=12000)
            return {'running': True, 'already_open': False}
        except PlaywrightError:
            # A failed navigation must not discard the browser / persistent data.
            return {'running': True, 'already_open': False,
                    'warning': 'Navegador iniciou, mas o site não terminou de carregar.'}
        except Exception:
            try:
                context.close()
            finally:
                self.contexts.pop(pid, None)
            raise

    def stop(self, pw, pid):
        context = self.contexts.pop(pid, None)
        if context is None:
            return {'running': False}
        context.close()
        return {'running': False}

    def frame(self, pw, pid):
        return self.page(pid).screenshot(type='jpeg', quality=68, timeout=8000,
                                         animations='disabled', scale='css')

    def act(self, pw, pid, data):
        page = self.page(pid)
        kind = data.get('type')
        if kind == 'click':
            x, y = data.get('x'), data.get('y')
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not 0 <= x <= 500 or not 0 <= y <= 1200:
                raise ValueError('Coordenadas inválidas.')
            page.mouse.click(x, y)
        elif kind == 'type':
            content = data.get('text')
            if not isinstance(content, str) or len(content) > 2048:
                raise ValueError('Texto inválido.')
            page.keyboard.insert_text(content)
        elif kind == 'key':
            key = data.get('key')
            if key not in KEYS:
                raise ValueError('Tecla não permitida.')
            page.keyboard.press(key)
        elif kind == 'scroll':
            delta = data.get('delta')
            if not isinstance(delta, int) or abs(delta) > 900:
                raise ValueError('Rolagem inválida.')
            page.mouse.wheel(0, delta)
        elif kind == 'back':
            page.go_back(wait_until='domcontentloaded', timeout=8000)
        elif kind == 'reload':
            page.reload(wait_until='domcontentloaded', timeout=8000)
        else:
            raise ValueError('Ação desconhecida.')
        return {'ok': True}


worker = BrowserWorker()


@app.before_request
def security():
    if request.path == '/healthz':
        return None
    secret = os.environ.get('NEXORA_RUNNER_KEY', '')
    if len(secret) < 32:
        return jsonify(error='Configure NEXORA_RUNNER_KEY (32+ caracteres) no executor.'), 503
    provided = request.headers.get('Authorization', '')
    if not provided.startswith('Bearer ') or not hmac.compare_digest(provided[7:], secret):
        return jsonify(error='Chave de executor inválida.'), 401
    if request.method == 'POST' and (request.mimetype != 'application/json'
                                      or (request.content_length or 0) > 8192):
        return jsonify(error='Requisição inválida.'), 415


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/healthz')
def public_health():
    return jsonify(healthy=True)


@app.get('/v1/health')
def health():
    return jsonify(ok=True, browser=True, mode='remote', max_profiles=MAX_PROFILES)


@app.get('/v1/status/<pid>')
def status(pid):
    try:
        return jsonify(worker.run('status', valid_id(pid)))
    except Exception:
        return jsonify(error='Não foi possível verificar o perfil.'), 503


@app.post('/v1/start')
def start():
    try:
        data = request.get_json()
        return jsonify(worker.run('start', valid_id(data.get('id')), valid_url(data.get('url'))))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception('Falha ao iniciar Chromium')
        return jsonify(error='Falha ao abrir Chromium no executor. Verifique o serviço.'), 503


@app.post('/v1/stop')
def stop():
    try:
        data = request.get_json()
        return jsonify(worker.run('stop', valid_id(data.get('id'))))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Falha ao encerrar perfil.'), 503


@app.get('/v1/frame/<pid>')
def frame(pid):
    try:
        shot = worker.run('frame', valid_id(pid))
        return Response(shot, content_type='image/jpeg')
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    except Exception:
        return jsonify(error='Não foi possível capturar navegador.'), 503


@app.post('/v1/act')
def act():
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Ação inválida.')
        return jsonify(worker.run('act', valid_id(data.get('id')), data))
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Não foi possível interagir com navegador.'), 503


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8080'))
    app.run(host='0.0.0.0', port=port, threaded=True)
